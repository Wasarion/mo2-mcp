"""The MO2 tools exposed over MCP. Handlers run on MO2's GUI thread unless marked otherwise.

create_separator, rename_mod, get_mod_conflicts, read_log and the wait-for-refresh helper follow the
approach of Antiarc123's "MCP - MO2" plugin (Nexus Mods site mod 2549, GPL-3.0-or-later).
"""

from __future__ import annotations

import collections
import logging
import os
import re
import shutil
import struct
import threading
import time
from typing import Any, Callable

import mobase
from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QAction, QTextDocument
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QMainWindow, QTreeWidget

from .mcp import Tool, ToolError
from .espm import light_verdict, read_plugin
from .procs import RunTracker
from .skse import dll_file_version, parse_skse_log

log = logging.getLogger("mo2_mcp")

MAX_WAIT = 600  # seconds one wait_for_run or wait_for_download call may block
REFRESH_WAIT = 120  # seconds to wait for MO2 to finish a refresh
BAD_NAME = re.compile(r'[\\/:*?"<>|]')


def _flag(state: Any, flag: Any) -> bool:
    return (int(state) & int(flag)) != 0


def _walk_visible(root: str) -> tuple[list[str], list[str]]:
    """Files under root as MO2's Data tab sees them, and what MO2 hides (*.mohidden files and folders)."""
    visible: list[str] = []
    hidden: list[str] = []
    for dirpath, dirs, fnames in os.walk(root):
        for d in [d for d in dirs if d.lower().endswith(".mohidden")]:
            dirs.remove(d)
            hidden.append(os.path.relpath(os.path.join(dirpath, d), root).replace("\\", "/") + "/")
        for f in fnames:
            rel = os.path.relpath(os.path.join(dirpath, f), root).replace("\\", "/")
            if f.lower().endswith(".mohidden"):
                hidden.append(rel)
            elif rel.lower() != "meta.ini":
                visible.append(rel)
    return visible, hidden


def _child_dir(path: str, *names: str) -> str | None:
    """path/names... matched case-insensitively (mods ship 'SKSE/Plugins', 'skse/plugins', ...)."""
    for name in names:
        try:
            match = next((e for e in os.listdir(path) if e.lower() == name.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        path = os.path.join(path, match)
    return path if os.path.isdir(path) else None


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not name or BAD_NAME.search(name) or name.endswith((".", " ")) or len(name) > 200:
        raise ToolError('Invalid name. Avoid \\ / : * ? " < > | and a trailing dot or space.')
    return name


class Mo2Tools:
    def __init__(
        self,
        organizer: mobase.IOrganizer,
        runs: RunTracker,
        confirm_install: Callable[[str, str], bool],
        invoke: Callable[[Callable[[], Any], float], Any],
        main_window: Callable[[], QMainWindow | None] = lambda: None,
    ):
        self.org = organizer
        self.main_window = main_window  # MO2's window, once its UI is up (for the profile box)
        self.runs = runs
        self.confirm_install = confirm_install
        self.invoke = invoke  # run something on the GUI thread (for worker-thread tools)
        # Downloads started by download_mod, keyed by our own id: (mod_id, file_id, start time, downloads folder).
        # MO2's own download ids are not stable (its list is re-sorted), so finished archives are found by their .meta.
        self._dl_lock = threading.Lock()
        self._downloads: dict[int, tuple[int, int, float, str]] = {}

    # -- helpers ---------------------------------------------------------------
    def _mod_name(self, name: str) -> str:
        mods = list(self.org.modList().allMods())
        if name in mods:
            return name
        lower = {m.lower(): m for m in mods}
        for candidate in (name.lower(), name.lower() + "_separator"):
            if candidate in lower:
                return lower[candidate]
        raise ToolError(f"No mod named '{name}'. Use list_mods to see exact names.")

    def _plugin_name(self, name: str) -> str:
        names = list(self.org.pluginList().pluginNames())
        lower = {p.lower(): p for p in names}
        if name.lower() in lower:
            return lower[name.lower()]
        raise ToolError(f"No plugin named '{name}'. Use list_plugins to see exact names.")

    def _mods_in_order(self) -> list[str]:
        ml = self.org.modList()
        out = []
        for name in ml.allModsByProfilePriority():
            mod = ml.getMod(name)
            if mod is None or mod.isOverwrite() or mod.isBackup():
                continue
            out.append(name)
        return out

    def _ini_path(self) -> str:
        return os.path.join(self.org.basePath(), "ModOrganizer.ini")

    def _name_free(self, name: str) -> None:
        taken = any(n.lower() == name.lower() for n in self.org.modList().allMods())
        if taken or os.path.exists(os.path.join(self.org.modsPath(), name)):
            raise ToolError(f"A mod or folder named '{name}' already exists.")

    def _refresh_and_wait(self, timeout: float = REFRESH_WAIT) -> bool:
        """Start a refresh and wait until MO2 has finished it. Worker threads only."""
        done = threading.Event()

        def start() -> None:
            self.org.onNextRefresh(done.set, False)
            self.org.refresh(True)

        self.invoke(start, 60)
        return done.wait(timeout)

    @staticmethod
    def _find_download(folder: str, mod_id: int, file_id: int, since: float) -> str | None:
        """Newest finished archive in folder whose .meta names this Nexus mod and file, written after since."""
        best: tuple[float, str] | None = None
        try:
            names = os.listdir(folder)
        except OSError:
            return None
        for meta in names:
            if not meta.lower().endswith(".meta"):
                continue
            archive = meta[:-5]
            path = os.path.join(folder, archive)
            if archive.lower().endswith(".unfinished") or not os.path.isfile(path):
                continue
            mtime = os.path.getmtime(path)
            if mtime < since:
                continue
            try:
                with open(os.path.join(folder, meta), encoding="utf-8", errors="replace") as f:
                    keys = dict(line.strip().split("=", 1) for line in f if "=" in line)
            except OSError:
                continue
            if keys.get("modID") == str(mod_id) and keys.get("fileID") == str(file_id):
                if best is None or mtime > best[0]:
                    best = (mtime, archive)
        return best[1] if best else None

    def _download_result(self, dl_id: int, timeout: float) -> dict[str, Any]:
        """Wait up to timeout for the archive to appear in the downloads folder. Worker threads only."""
        with self._dl_lock:
            mod_id, file_id, since, folder = self._downloads[dl_id]
        deadline = time.monotonic() + timeout
        while True:
            archive = self._find_download(folder, mod_id, file_id, since)
            if archive or time.monotonic() >= deadline:
                break
            time.sleep(1.0)
        result: dict[str, Any] = {"download_id": dl_id}
        if archive:
            return result | {"status": "complete", "archive": archive,
                             "note": "Install it with install_mod (archive name above) once the user agrees."}
        return result | {"status": "not finished",
                         "note": "Not in the downloads folder yet; call wait_for_download again. "
                                 "If MO2's Downloads tab shows it as failed or paused, tell the user."}

    # -- read tools --------------------------------------------------------------
    def get_status(self, args: dict[str, Any]) -> Any:
        game = self.org.managedGame()
        ml, pl = self.org.modList(), self.org.pluginList()
        all_mods = self._mods_in_order()
        seps = [m for m in all_mods if ml.getMod(m).isSeparator()]
        mods = [m for m in all_mods if m not in set(seps)]
        enabled = [m for m in mods if _flag(ml.state(m), mobase.ModState.ACTIVE)]
        plugins = list(pl.pluginNames())
        active_plugins = [p for p in plugins if pl.state(p) == mobase.PluginState.ACTIVE]
        profile = self.org.profile()
        return {
            "mo2_version": self.org.appVersion().displayString(),
            "game": game.gameName(),
            "game_version": game.gameVersion(),
            "game_dir": game.gameDirectory().absolutePath(),
            "instance_dir": self.org.basePath(),
            "mods_dir": self.org.modsPath(),
            "downloads_dir": self.org.downloadsPath(),
            "overwrite_dir": self.org.overwritePath(),
            "profile": self.org.profileName(),
            "profile_dir": self.org.profilePath(),
            "profile_local_saves": profile.localSavesEnabled(),
            "profile_local_ini": profile.localSettingsEnabled(),
            "mods": {"total": len(mods), "enabled": len(enabled), "separators": len(seps)},
            "plugins": {"total": len(plugins), "enabled": len(active_plugins)},
            "overwrite_files": sum(len(f) for _, _, f in os.walk(self.org.overwritePath())),
            "runs_in_progress": [r.describe() for r in self.runs.active()],
        }

    def list_mods(self, args: dict[str, Any]) -> Any:
        ml = self.org.modList()
        text = str(args.get("filter", "")).lower()
        only_enabled = bool(args.get("enabled_only", False))
        want_sep = str(args.get("separator", "")).lower().removesuffix("_separator")
        lines = ["# priority | +enabled/-disabled | name   (separators shown as == name ==; higher priority wins conflicts)"]
        current_sep = ""
        for name in self._mods_in_order():
            mod = ml.getMod(name)
            if mod.isSeparator():
                current_sep = name.removesuffix("_separator")
                if (not want_sep or current_sep.lower() == want_sep) and not text:
                    lines.append(f"{ml.priority(name):>4}   == {current_sep} ==")
                continue
            if want_sep and current_sep.lower() != want_sep:
                continue
            on = _flag(ml.state(name), mobase.ModState.ACTIVE)
            if only_enabled and not on:
                continue
            if text and text not in name.lower():
                continue
            lines.append(f"{ml.priority(name):>4} {'+' if on else '-'} {name}")
        if len(lines) == 1:
            return "No mods match."
        return "\n".join(lines)

    def list_plugins(self, args: dict[str, Any]) -> Any:
        pl = self.org.pluginList()
        text = str(args.get("filter", "")).lower()
        only_enabled = bool(args.get("enabled_only", False))
        names = sorted(pl.pluginNames(), key=pl.priority)
        lines = ["# priority | load order | +enabled/-disabled | name [flags] <- mod   (flags: M=master, L=light, Md=medium, E=no records)"]
        for name in names:
            state = pl.state(name)
            on = state == mobase.PluginState.ACTIVE
            if only_enabled and not on:
                continue
            if text and text not in name.lower():
                continue
            flags = []
            if pl.isMasterFlagged(name) or pl.hasMasterExtension(name):
                flags.append("M")
            if pl.isLightFlagged(name) or pl.hasLightExtension(name):
                flags.append("L")
            if getattr(pl, "isMediumFlagged", None) and pl.isMediumFlagged(name):
                flags.append("Md")
            if pl.hasNoRecords(name):
                flags.append("E")
            lo = pl.loadOrder(name)
            lo_txt = f"{lo:>4}" if lo >= 0 else "   -"
            missing = " MISSING" if state == mobase.PluginState.MISSING else ""
            lines.append(
                f"{pl.priority(name):>4} {lo_txt} {'+' if on else '-'} {name}"
                f"{' [' + ''.join(flags) + ']' if flags else ''}{missing} <- {pl.origin(name)}"
            )
        if len(lines) == 1:
            return "No plugins match."
        return "\n".join(lines)

    def get_mod(self, args: dict[str, Any]) -> Any:
        ml = self.org.modList()
        name = self._mod_name(args["name"])
        mod = ml.getMod(name)
        path = mod.absolutePath()
        files, hidden = _walk_visible(path)
        info: dict[str, Any] = {
            "name": name,
            "enabled": _flag(ml.state(name), mobase.ModState.ACTIVE),
            "priority": ml.priority(name),
            "separator": mod.isSeparator(),
            "version": mod.version().displayString(),
            "nexus_id": mod.nexusId(),
            "url": mod.url(),
            "categories": list(mod.categories()),
            "installation_file": mod.installationFile(),
            "comments": mod.comments(),
            "notes": mod.notes()[:2000],
            "path": path,
            "plugins": sorted(f for f in files if "/" not in f and f.lower().endswith((".esp", ".esm", ".esl"))),
            "file_count": len(files),
            "hidden_by_mo2": len(hidden),
        }
        if args.get("list_files"):
            limit = int(args.get("max_files", 300))
            info["files"] = sorted(files)[:limit]
            if hidden:
                info["hidden_files"] = sorted(hidden)[:limit]
            if len(files) > limit:
                info["files_truncated"] = len(files) - limit
        return info

    def file_origins(self, args: dict[str, Any]) -> Any:
        rel = str(args["path"]).replace("/", "\\").lstrip("\\")
        if rel.lower().startswith("data\\"):
            rel = rel[5:]
        origins = list(self.org.getFileOrigins(rel))
        if not origins:
            raise ToolError(f"'{rel}' is not in the virtual Data folder.")
        return {"path": rel, "winner": origins[0], "also_provided_by": origins[1:], "resolved": self.org.resolvePath(rel)}

    def get_mod_conflicts(self, args: dict[str, Any]) -> Any:
        ml = self.org.modList()
        name = self._mod_name(args["name"])
        mod = ml.getMod(name)
        if mod.isSeparator():
            raise ToolError(f"'{name}' is a separator.")
        if not _flag(ml.state(name), mobase.ModState.ACTIVE):
            raise ToolError(f"'{name}' is disabled. MO2 only tracks conflicts of enabled mods.")
        examples = min(max(0, int(args.get("examples", 5))), 100)
        root = mod.absolutePath()
        beats: dict[str, list[str]] = collections.defaultdict(list)
        loses: dict[str, list[str]] = collections.defaultdict(list)
        checked = unique = 0
        truncated = False
        visible, _hidden = _walk_visible(root)
        for shown in visible:
            if checked >= 50000:
                truncated = True
                break
            checked += 1
            origins = list(self.org.getFileOrigins(shown.replace("/", os.sep)))
            if name not in origins:
                continue
            if origins[0] == name:
                if len(origins) == 1:
                    unique += 1
                for other in origins[1:]:
                    beats[other].append(shown)
            else:
                loses[origins[0]].append(shown)
        known = set(ml.allMods())

        def summary(d: dict[str, list[str]]) -> list[dict[str, Any]]:
            rows = sorted(d.items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))
            return [{"mod": k, "priority": ml.priority(k) if k in known else None,
                     "files": len(v), "examples": v[:examples]} for k, v in rows]

        return {
            "mod": name,
            "priority": ml.priority(name),
            "files_checked": checked,
            "truncated": truncated,
            "files_without_conflict": unique,
            "overrides": summary(beats),
            "overridden_by": summary(loses),
            "note": "Loose files only, without files MO2 hides (.mohidden); BSA contents are not compared. 'data' means the game's own Data folder.",
        }

    def list_skse_plugins(self, args: dict[str, Any]) -> Any:
        ml = self.org.modList()
        game = self.org.managedGame()
        log_path = os.path.join(game.documentsDirectory().absolutePath(), "SKSE", "skse64.log")
        log = None
        log_time = None
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as f:
                log = parse_skse_log(f.read())
            log_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(log_path)))

        sources: list[tuple[str, str, bool, int | None]] = []  # (mod, folder, enabled, priority)
        for name in self._mods_in_order():
            mod = ml.getMod(name)
            if mod.isSeparator():
                continue
            sources.append((name, mod.absolutePath(), _flag(ml.state(name), mobase.ModState.ACTIVE), ml.priority(name)))
        sources.append(("(game Data folder)", game.dataDirectory().absolutePath(), True, None))

        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for mod_name, folder, enabled, priority in sources:
            plugins_dir = _child_dir(folder, "SKSE", "Plugins")
            if plugins_dir is None:
                continue
            for dll in sorted((f for f in os.listdir(plugins_dir) if f.lower().endswith(".dll")), key=str.lower):
                row: dict[str, Any] = {"dll": dll, "mod": mod_name, "mod_enabled": enabled}
                if priority is not None:
                    row["priority"] = priority
                if enabled:
                    origins = list(self.org.getFileOrigins(os.path.join("SKSE", "Plugins", dll)))
                    winner = origins[0] if origins else mod_name
                    if winner != mod_name and not (mod_name.startswith("(") and winner == "data"):
                        row["status"] = f"overridden by {winner}"
                if "status" not in row:
                    if not enabled:
                        row["status"] = "mod disabled"
                    elif log is None:
                        row["status"] = "no SKSE log yet"
                    else:
                        entry = log.entries.get(dll.lower())
                        if entry is None:
                            row["status"] = "not in the SKSE log (added after the last game start?)"
                            row["problem"] = True
                        else:
                            if entry.loaded:
                                row["status"] = "loaded"
                            elif entry.helper:
                                row["status"] = "helper DLL, not an SKSE plugin (SKSE skips it)"
                            else:
                                row["status"] = f"not loaded: {entry.result}"
                                row["problem"] = True
                            if entry.name:
                                row["name"] = entry.name
                            if entry.version:
                                row["version"] = entry.version
                        seen.add(dll.lower())
                file_version = dll_file_version(os.path.join(plugins_dir, dll))
                if file_version:
                    row["file_version"] = file_version
                rows.append(row)

        only_in_log = sorted(e.dll for k, e in (log.entries.items() if log else []) if k not in seen)
        summary = {
            "dlls": len(rows),
            "in_enabled_mods": sum(1 for r in rows if r["mod_enabled"] and not r["status"].startswith("overridden")),
            "loaded": sum(1 for r in rows if r["status"] == "loaded"),
            "problems": sum(1 for r in rows if r.get("problem")),
            "in_disabled_mods": sum(1 for r in rows if not r["mod_enabled"]),
        }
        text = str(args.get("filter", "")).lower()
        if text:
            rows = [r for r in rows if text in r["dll"].lower() or text in r["mod"].lower() or text in r.get("name", "").lower()]
        if args.get("enabled_only"):
            rows = [r for r in rows if r["mod_enabled"]]
        if args.get("problems_only"):
            rows = [r for r in rows if r.get("problem")]
        result: dict[str, Any] = {
            "skse_log": log_path if log else f"not found: {log_path}",
            "summary": summary,
            "plugins": rows,
        }
        if log:
            result["skse_version"] = log.skse_version
            result["log_written"] = log_time
            result["note"] = "Loaded/not loaded is from the last game start; mods changed since then are not reflected."
        if only_in_log:
            result["in_log_but_not_found"] = only_in_log
        return result

    def plugin_header(self, args: dict[str, Any]) -> Any:
        names = args.get("names")
        official = re.compile(r"^(skyrim|update|dawnguard|hearthfires|dragonborn)\.esm$|^cc.*\.es[ml]$", re.IGNORECASE)

        def collect() -> tuple[list[tuple[str, str, str]], dict[str, list[str]], int, int]:
            pl = self.org.pluginList()
            enabled = [p for p in pl.pluginNames() if pl.state(p) == mobase.PluginState.ACTIVE]
            if names:
                chosen = [self._plugin_name(n) for n in names]
            else:
                chosen = [p for p in enabled if not official.match(p)
                          and not (pl.isLightFlagged(p) or pl.hasLightExtension(p))]
            dependents: dict[str, list[str]] = collections.defaultdict(list)
            for p in enabled:
                for m in pl.masters(p):
                    dependents[m.lower()].append(p)
            full = sum(1 for p in enabled if not (pl.isLightFlagged(p) or pl.hasLightExtension(p)))
            light = len(enabled) - full
            return [(p, pl.origin(p), self.org.resolvePath(p)) for p in sorted(chosen, key=pl.priority)], dependents, full, light

        chosen, dependents, full, light = self.invoke(collect, 60)
        rows: list[dict[str, Any]] = []
        for name, origin, path in chosen:
            row: dict[str, Any] = {"plugin": name, "mod": origin}
            if not path or not os.path.isfile(path):
                rows.append(row | {"error": "File not found through MO2's virtual Data folder."})
                continue
            try:
                info = read_plugin(path)
            except (OSError, ValueError, struct.error) as e:
                rows.append(row | {"error": str(e)})
                continue
            code, why = light_verdict(info)
            flags = "".join(f for f, on in (("M", info.master_flag), ("L", info.light)) if on)
            row |= {
                "flags": flags,
                "header_version": info.form_version,
                "masters": info.masters,
                "records": info.records,
                "new_records": info.new_records,
            }
            if info.new_records:
                row["new_id_range"] = f"0x{info.min_new_id:06X}-0x{info.max_new_id:06X}"
            row["light"] = code
            row["why"] = why
            users = dependents.get(name.lower(), [])
            if users and code in ("needs_compacting", "needs_header_171"):
                row["used_as_master_by"] = users
            if info.notes:
                row["notes"] = info.notes
            rows.append(row)

        if args.get("candidates_only"):
            rows = [r for r in rows if r.get("light") in ("flag_as_is", "needs_header_171")]
        result: dict[str, Any] = {"plugins": rows}
        if not names:
            as_is = sum(1 for r in rows if r.get("light") == "flag_as_is")
            result["summary"] = {
                "enabled_full_plugins": full,
                "enabled_light_plugins": light,
                "full_plugin_limit": 254,
                "could_be_flagged_light_as_is": as_is,
                "full_plugins_if_flagged": full - as_is,
            }
        result["note"] = ("This tool only reads files; flag plugins in xEdit. Do it before starting a playthrough, not on an "
                          "existing save. xEdit (-PseudoESL) and ESLifier also check facegen and INI references.")
        return result

    def list_executables(self, args: dict[str, Any]) -> Any:
        s = QSettings(self._ini_path(), QSettings.Format.IniFormat)
        out = []
        size = s.beginReadArray("customExecutables")
        for i in range(size):
            s.setArrayIndex(i)
            out.append({
                "title": s.value("title", ""),
                "binary": s.value("binary", ""),
                "arguments": s.value("arguments", ""),
                "working_dir": s.value("workingDirectory", ""),
            })
        s.endArray()
        return out

    def list_runs(self, args: dict[str, Any]) -> Any:
        return [r.describe() for r in self.runs.all()] or "Nothing has been started through this plugin yet."

    def read_log(self, args: dict[str, Any]) -> Any:
        logs = os.path.join(self.invoke(self.org.basePath, 30), "logs")
        which = args.get("log", "mo")
        if which == "mo":
            path = os.path.join(logs, "mo_interface.log")
        elif which == "usvfs":
            found = sorted((f for f in os.listdir(logs) if f.lower().startswith("usvfs")),
                           key=lambda f: os.path.getmtime(os.path.join(logs, f))) if os.path.isdir(logs) else []
            if not found:
                raise ToolError("No usvfs log found.")
            path = os.path.join(logs, found[-1])
        else:
            raise ToolError("log must be 'mo' or 'usvfs'.")
        if not os.path.isfile(path):
            raise ToolError(f"Log not found: {path}")
        n = min(max(1, int(args.get("lines", 150))), 3000)
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        needle = str(args.get("contains", "")).lower()
        if needle:
            lines = [ln for ln in lines if needle in ln.lower()]
        return f"# {path} (last {min(n, len(lines))} of {len(lines)} lines)\n" + "\n".join(lines[-n:])

    # -- write tools --------------------------------------------------------------
    def set_mods_enabled(self, args: dict[str, Any]) -> Any:
        names = [self._mod_name(n) for n in args["names"]]
        ml = self.org.modList()
        for n in names:
            if ml.getMod(n).isSeparator():
                raise ToolError(f"'{n}' is a separator.")
        ml.setActive(names, bool(args["enabled"]))
        return {n: _flag(ml.state(n), mobase.ModState.ACTIVE) for n in names}

    def set_mod_priority(self, args: dict[str, Any]) -> Any:
        ml = self.org.modList()
        name = self._mod_name(args["name"])
        target = args.get("priority")
        anchor = args.get("after")
        if (target is None) == (anchor is None):
            raise ToolError("Give exactly one of 'priority' or 'after'.")
        if anchor is not None:
            a = self._mod_name(str(anchor))
            pa, pn = ml.priority(a), ml.priority(name)
            target = pa if pn < pa else pa + 1
        assert target is not None
        if not ml.setPriority(name, int(target)):
            raise ToolError(f"MO2 refused to move '{name}' to priority {target}.")
        return {"name": name, "priority": ml.priority(name)}

    def set_plugins_enabled(self, args: dict[str, Any]) -> Any:
        pl = self.org.pluginList()
        names = [self._plugin_name(n) for n in args["names"]]
        state = mobase.PluginState.ACTIVE if args["enabled"] else mobase.PluginState.INACTIVE
        for n in names:
            pl.setState(n, state)
        return {n: pl.state(n) == mobase.PluginState.ACTIVE for n in names}

    def set_plugin_priority(self, args: dict[str, Any]) -> Any:
        pl = self.org.pluginList()
        name = self._plugin_name(args["name"])
        if not pl.setPriority(name, int(args["priority"])):
            raise ToolError(f"MO2 refused to move '{name}' (masters must stay above their dependents).")
        return {"name": name, "priority": pl.priority(name), "load_order": pl.loadOrder(name)}

    def refresh(self, args: dict[str, Any]) -> Any:
        if self._refresh_and_wait():
            return "MO2 refreshed."
        return f"Refresh started but not finished after {REFRESH_WAIT} s; MO2 may still be busy."

    def create_separator(self, args: dict[str, Any]) -> Any:
        label = _check_name(args["name"]).removesuffix("_separator")
        internal = label + "_separator"
        if args.get("after") is not None and args.get("priority") is not None:
            raise ToolError("Give at most one of 'priority' or 'after'.")

        def create() -> None:
            self._name_free(internal)
            if self.org.createMod(mobase.GuessedString(internal)) is None:
                raise ToolError("MO2 did not create the separator.")

        self.invoke(create, 60)
        if not self._refresh_and_wait():
            return {"separator": label, "note": "Created, but MO2 is still refreshing; place it later with set_mod_priority."}
        move = {k: args[k] for k in ("after", "priority") if args.get(k) is not None}
        if move:
            return self.invoke(lambda: self.set_mod_priority({"name": internal, **move}), 60) | {"separator": label}
        return {"separator": label, "name": internal, "priority": self.invoke(lambda: self.org.modList().priority(internal), 60)}

    def list_profiles(self, args: dict[str, Any]) -> Any:
        active = self.org.profileName()
        base = os.path.dirname(os.path.normpath(self.org.profilePath()))
        names = sorted((d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))), key=str.lower)
        return {"active": active, "profiles": [{"name": n, "active": n == active} for n in names]}

    def list_notifications(self, args: dict[str, Any]) -> Any:
        """MO2 gives plugins no access to its notifications, so read them from MO2's own window."""
        window = self.main_window()
        if window is None:
            raise ToolError("MO2's main window is not ready yet; try again in a moment.")
        action = window.findChild(QAction, "actionNotifications")
        if action is None:
            raise ToolError("MO2's notifications button was not found; this MO2 version is not supported.")
        if not action.isEnabled():  # MO2 disables the button when it counts no notifications
            return {"count": 0, "notifications": []}
        if QApplication.activeModalWidget() is not None:
            raise ToolError("A dialog is open in MO2 (or MO2 is locked by a running program). Close it and try again.")

        found: dict[str, Any] = {}

        def harvest(tries: int = 0) -> None:
            dialog = next((d for d in window.findChildren(QDialog) if d.objectName() == "ProblemsDialog" and d.isVisible()), None)
            if dialog is None:
                if tries < 40:
                    QTimer.singleShot(50, lambda: harvest(tries + 1))
                return
            tree = dialog.findChild(QTreeWidget, "problemsWidget")
            rows = []
            items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())] if tree is not None else []
            for item in items:
                if item is None or tree is None:
                    continue
                details = str(item.data(0, Qt.ItemDataRole.UserRole) or "")  # the full description, may be HTML
                if not details and item.text(0).startswith("("):
                    continue  # MO2's "(There are no notifications)" placeholder
                doc = QTextDocument()
                doc.setHtml(details)
                rows.append({"problem": item.text(0), "details": doc.toPlainText().strip(),
                             "guided_fix_in_mo2": tree.itemWidget(item, 1) is not None})
            found["rows"] = rows
            dialog.reject()  # close MO2's window again

        QTimer.singleShot(0, harvest)
        action.trigger()  # opens MO2's notifications window; harvest() runs inside it and closes it
        if "rows" not in found:
            raise ToolError("Could not read MO2's notifications window. If it is still open, close it in MO2.")
        return {"count": len(found["rows"]), "notifications": found["rows"]}

    def _profile_box(self) -> QComboBox:
        window = self.main_window()
        if window is None:
            raise ToolError("MO2's main window is not ready yet; try again in a moment.")
        box = window.findChild(QComboBox, "profileBox")
        if box is None:
            raise ToolError("MO2's profile box was not found; this MO2 version is not supported for switching profiles.")
        return box

    def switch_profile(self, args: dict[str, Any]) -> Any:
        want = str(args["name"])

        def switch() -> tuple[str, str, bool]:
            box = self._profile_box()
            # Item 0 is "<Manage...>", which opens a dialog; only items 1.. are profiles.
            profiles = [box.itemText(i) for i in range(1, box.count())]
            match = next((p for p in profiles if p.lower() == want.lower()), None)
            if match is None:
                raise ToolError(f"No profile named '{want}'. Profiles: {', '.join(profiles)}.")
            old = self.org.profileName()
            if match == old:
                return old, old, False
            if not box.isEnabled():
                raise ToolError("MO2's profile box is locked, usually because a program started through MO2 "
                                "(the game, xEdit…) is still running. Close it and try again.")
            box.setCurrentText(match)  # runs MO2's own switch: saves the lists, activates, refreshes
            return old, self.org.profileName(), True

        old, now, changed = self.invoke(switch, 120)
        if not changed:
            return {"profile": now, "note": "That profile is already active."}
        if now.lower() != want.lower():
            raise ToolError(f"MO2 did not switch profiles; '{now}' is still active. See read_log.")
        return {"previous": old, "profile": now, "refreshed": self._refresh_and_wait()}

    def create_mod_from_overwrite(self, args: dict[str, Any]) -> Any:
        name = _check_name(args["name"])
        into = bool(args.get("into_existing", False))
        replace = bool(args.get("replace_files", False))
        if args.get("after") is not None and args.get("priority") is not None:
            raise ToolError("Give at most one of 'priority' or 'after'.")

        overwrite = self.invoke(self.org.overwritePath, 30)
        entries = sorted(e for e in os.listdir(overwrite) if e.lower() != "meta.ini") if os.path.isdir(overwrite) else []
        if not entries:
            raise ToolError("Overwrite is empty; there is nothing to move.")
        only = args.get("only")
        if only:
            by_lower = {e.lower(): e for e in entries}
            missing = [o for o in only if str(o).lower() not in by_lower]
            if missing:
                raise ToolError(f"Not in Overwrite: {', '.join(missing)}. Overwrite holds: {', '.join(entries)}.")
            entries = sorted({by_lower[str(o).lower()] for o in only})
        files: list[str] = []
        for entry in entries:
            src = os.path.join(overwrite, entry)
            if os.path.isdir(src):
                for dirpath, _dirs, fnames in os.walk(src):
                    for f in fnames:
                        files.append(os.path.relpath(os.path.join(dirpath, f), overwrite).replace("\\", "/"))
            else:
                files.append(entry)
        files.sort()

        def resolve() -> tuple[str, str]:
            if into:
                target = self._mod_name(name)
                mod = self.org.modList().getMod(target)
                if mod.isSeparator() or mod.isOverwrite() or mod.isForeign() or mod.isBackup():
                    raise ToolError(f"'{target}' cannot receive files (separator, Overwrite, DLC/unmanaged, or a backup).")
                return target, mod.absolutePath()
            self._name_free(name)
            return name, os.path.join(self.org.modsPath(), name)

        target, target_path = self.invoke(resolve, 60)
        clashes = [f for f in files if os.path.exists(os.path.join(target_path, f))] if into else []
        plan: dict[str, Any] = {
            "mod": target,
            "new_mod": not into,
            "moves": entries,
            "file_count": len(files),
            "files": files[:50],
        }
        if len(files) > 50:
            plan["files_truncated"] = len(files) - 50
        if clashes:
            plan["replaces"] = clashes[:50]
            plan["replaces_count"] = len(clashes)
        if args.get("dry_run"):
            return plan | {"dry_run": True, "note": "Nothing was moved."}
        if clashes and not replace:
            raise ToolError(
                f"{len(clashes)} file(s) already exist in '{target}' (e.g. {clashes[0]}). "
                "Pass replace_files=true to replace them, or use a new mod name. Nothing was moved.")

        if not into:
            def create() -> str:
                mod = self.org.createMod(mobase.GuessedString(name))
                if mod is None:
                    raise ToolError("MO2 did not create the mod. Nothing was moved.")
                return mod.absolutePath()
            target_path = self.invoke(create, 60)

        moved = 0
        try:
            for rel in files:
                src = os.path.join(overwrite, rel)
                dst = os.path.join(target_path, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.replace(src, dst)  # same drive: an instant rename
                except OSError:
                    shutil.move(src, dst)  # another drive: copy, then remove the source
                moved += 1
        except OSError as e:
            raise ToolError(
                f"Stopped after moving {moved} of {len(files)} file(s) into '{target}': {e}. "
                "The rest are still in Overwrite; nothing was deleted.") from e
        for entry in entries:  # remove the folders the move emptied, never a file
            top = os.path.join(overwrite, entry)
            if os.path.isdir(top):
                for dirpath, _dirs, _files in sorted(os.walk(top), key=lambda w: -len(w[0])):
                    try:
                        os.rmdir(dirpath)
                    except OSError:
                        pass

        result = {k: plan[k] for k in ("mod", "new_mod", "moves", "file_count")} | {"moved": moved}
        if clashes:
            result["replaced"] = len(clashes)
        if not self._refresh_and_wait():
            return result | {"note": "Files moved, but MO2 is still refreshing; place and enable the mod later."}
        move = {k: args[k] for k in ("after", "priority") if args.get(k) is not None}
        if move:
            result["priority"] = self.invoke(lambda: self.set_mod_priority({"name": target, **move}), 60)["priority"]
        if "enable" in args or not into:  # a new mod is enabled unless enable=false; an existing one keeps its state
            want = bool(args.get("enable", True))
            result["enabled"] = self.invoke(lambda: self.set_mods_enabled({"names": [target], "enabled": want}), 60)[target]
        if "priority" not in result:
            result["priority"] = self.invoke(lambda: self.org.modList().priority(target), 60)
        return result

    def rename_mod(self, args: dict[str, Any]) -> Any:
        ml = self.org.modList()
        old = self._mod_name(args["name"])
        mod = ml.getMod(old)
        if mod.isOverwrite() or mod.isForeign() or mod.isBackup():
            raise ToolError(f"'{old}' cannot be renamed (Overwrite, DLC/unmanaged, or a backup).")
        new = _check_name(args["new_name"])
        if mod.isSeparator() and not new.endswith("_separator"):
            new += "_separator"
        if new == old:
            raise ToolError("The new name is the same as the old one.")
        if new.lower() != old.lower():
            self._name_free(new)
        renamed = ml.renameMod(mod, new)
        if renamed is None:
            raise ToolError("MO2 did not rename the mod (see read_log).")
        return {"old": old, "new": renamed.name(), "priority": ml.priority(renamed.name())}

    def run_executable(self, args: dict[str, Any]) -> Any:
        exe = str(args["executable"])
        exe_args = [str(a) for a in args.get("args", [])]
        known = {e["title"].lower(): e["title"] for e in self.list_executables({})}
        if exe.lower() in known:
            title = known[exe.lower()]
        elif os.path.isabs(exe):
            title = exe
        else:
            raise ToolError(f"'{exe}' is not an MO2 executable. Known: {', '.join(known.values())}")
        handle = self.org.startApplication(title, exe_args, str(args.get("cwd", "")))
        if not handle or handle in (-1, 0xFFFFFFFFFFFFFFFF):
            raise ToolError(f"MO2 could not start '{title}'. Check MO2's log.")
        run = self.runs.add(title, exe_args, int(handle))
        return run.describe() | {"note": "Use wait_for_run to wait for it, then refresh if it wrote files."}

    def install_mod(self, args: dict[str, Any]) -> Any:
        path = str(args["archive"])
        if not os.path.isabs(path):
            path = os.path.join(self.org.downloadsPath(), path)
        if not os.path.isfile(path):
            raise ToolError(f"Archive not found: {path}")
        suggestion = str(args.get("name", ""))
        if not self.confirm_install(path, suggestion):
            raise ToolError("The user declined the installation in MO2.")
        mod = self.org.installMod(path, suggestion)
        if mod is None:
            raise ToolError("Installation cancelled or failed.")
        return {"installed": mod.name(), "priority": self.org.modList().priority(mod.name()), "enabled": False,
                "note": "New mods are installed disabled; enable with set_mods_enabled."}

    # -- worker-thread tools --------------------------------------------------------
    def wait_for_run(self, args: dict[str, Any]) -> Any:
        run = self.runs.get(int(args["run_id"]))
        if run is None:
            raise ToolError("Unknown run_id. Use list_runs.")
        timeout = min(float(args.get("timeout_seconds", 120)), MAX_WAIT)
        self.runs.wait(run, timeout)
        result = run.describe()
        if not run.running and args.get("refresh", True):
            result["refreshed"] = self._refresh_and_wait()
        elif run.running:
            result["note"] = "Still running; call wait_for_run again."
        return result

    def download_mod(self, args: dict[str, Any]) -> Any:
        """Start a Nexus download through MO2. MO2 uses its own Nexus login; this plugin never sees the API key."""
        mod_id, file_id = int(args["mod_id"]), int(args["file_id"])
        if mod_id <= 0 or file_id <= 0:
            raise ToolError("mod_id and file_id must be positive Nexus ids (from the mod page's Files tab).")
        timeout = min(float(args.get("wait_seconds", 300)), MAX_WAIT)

        since = time.time() - 2  # small margin for file-system timestamp rounding

        def start() -> tuple[int, str]:
            return int(self.org.downloadManager().startDownloadNexusFile(mod_id, file_id)), self.org.downloadsPath()

        mo2_id, folder = self.invoke(start, 60)
        if mo2_id < 0:
            raise ToolError("MO2 could not start the download. Is MO2 logged in to Nexus (Settings > Nexus)? See read_log.")
        with self._dl_lock:
            dl_id = len(self._downloads) + 1
            self._downloads[dl_id] = (mod_id, file_id, since, folder)
        log.info(f"Claude MCP: download {dl_id} started for Nexus mod {mod_id}, file {file_id}")
        return {"mod_id": mod_id, "file_id": file_id} | self._download_result(dl_id, timeout)

    def wait_for_download(self, args: dict[str, Any]) -> Any:
        dl_id = int(args["download_id"])
        with self._dl_lock:
            known = dl_id in self._downloads
        if not known:
            raise ToolError("Unknown download_id. Only downloads started with download_mod can be waited for.")
        return self._download_result(dl_id, min(float(args.get("timeout_seconds", 120)), MAX_WAIT))

    # -- registry ---------------------------------------------------------------------
    def tools(self) -> list[Tool]:
        s = {"type": "string"}
        b = {"type": "boolean"}
        names = {"type": "array", "items": {"type": "string"}}
        return [
            Tool("get_status", "Overview: MO2/game versions, paths, active profile, mod and plugin counts, files in Overwrite, running tools.",
                 {}, self.get_status),
            Tool("list_mods", "Left pane in priority order. Optional filters: substring, enabled only, or only mods under one separator.",
                 {"filter": s, "enabled_only": b, "separator": s}, self.list_mods),
            Tool("list_plugins", "Right pane (plugins) in load order with flags and providing mod.",
                 {"filter": s, "enabled_only": b}, self.list_plugins),
            Tool("get_mod", "Details of one mod: version, Nexus id, notes, plugins, optionally its file list.",
                 {"name": s, "list_files": b, "max_files": {"type": "integer"}}, self.get_mod, ["name"]),
            Tool("file_origins", "Which mod wins a file in the virtual Data folder, and which mods it overrides. Path relative to Data, e.g. 'meshes/x.nif'.",
                 {"path": s}, self.file_origins, ["path"]),
            Tool("get_mod_conflicts", "Loose-file conflicts of one enabled mod: which mods it overrides and which override it, with example files.",
                 {"name": s, "examples": {"type": "integer"}}, self.get_mod_conflicts, ["name"], timeout=180),
            Tool("read_log", "Last lines of MO2's log ('mo', default) or the newest usvfs log ('usvfs'), optionally only lines containing a text.",
                 {"log": {"type": "string", "enum": ["mo", "usvfs"]}, "lines": {"type": "integer"}, "contains": s},
                 self.read_log, main_thread=False),
            Tool("list_skse_plugins", "Every SKSE plugin DLL in the mods (enabled or not) and the game's Data folder: its mod, "
                 "whether another mod's copy wins, and whether it loaded in the last game start (from skse64.log, with the "
                 "plugin's name and version). Filters: text, enabled_only, problems_only.",
                 {"filter": s, "enabled_only": b, "problems_only": b}, self.list_skse_plugins),
            Tool("plugin_header", "Read plugin files directly: flags, header version, masters, record and new-record counts, and "
                 "whether each could be a light (ESL) plugin. Without names: every enabled plugin that isn't light yet "
                 "(Bethesda's own files skipped), with a count of full plugin slots. candidates_only keeps those that can "
                 "be flagged light without changing FormIDs. Reads files only.",
                 {"names": names, "candidates_only": b}, self.plugin_header, main_thread=False, timeout=900),
            Tool("list_executables", "Executables configured in MO2 (titles usable with run_executable).",
                 {}, self.list_executables),
            Tool("list_runs", "Programs started with run_executable and their status.",
                 {}, self.list_runs, main_thread=False),
            Tool("set_mods_enabled", "Enable or disable mods (left pane checkboxes).",
                 {"names": names, "enabled": b}, self.set_mods_enabled, ["names", "enabled"], writes=True),
            Tool("set_mod_priority", "Move a mod: give 'priority' (number) or 'after' (place it directly below another mod or separator).",
                 {"name": s, "priority": {"type": "integer"}, "after": s}, self.set_mod_priority, ["name"], writes=True),
            Tool("set_plugins_enabled", "Enable or disable plugins (right pane checkboxes).",
                 {"names": names, "enabled": b}, self.set_plugins_enabled, ["names", "enabled"], writes=True),
            Tool("set_plugin_priority", "Move a plugin to a priority (position in the right pane).",
                 {"name": s, "priority": {"type": "integer"}}, self.set_plugin_priority, ["name", "priority"], writes=True),
            Tool("refresh", "Refresh MO2 (like F5) and wait until it has finished, e.g. after a tool wrote files.",
                 {}, self.refresh, writes=True, main_thread=False, timeout=REFRESH_WAIT + 70),
            Tool("create_separator", "Create a separator; optionally place it with 'after' (below a mod/separator) or 'priority'.",
                 {"name": s, "after": s, "priority": {"type": "integer"}}, self.create_separator, ["name"],
                 writes=True, main_thread=False, timeout=REFRESH_WAIT + 140),
            Tool("list_notifications", "MO2's notifications (the warning-triangle list): each problem's text and details, "
                 "and whether MO2 offers a guided fix. Briefly opens MO2's notifications window and closes it.",
                 {}, self.list_notifications),
            Tool("list_profiles", "MO2 profiles and which one is active.",
                 {}, self.list_profiles),
            Tool("switch_profile", "Switch MO2's active profile, exactly as choosing it in MO2's profile box (MO2 saves the "
                 "current lists first). Refused while MO2 is locked by a running program.",
                 {"name": s}, self.switch_profile, ["name"], writes=True, main_thread=False, timeout=REFRESH_WAIT + 200),
            Tool("create_mod_from_overwrite",
                 "Move what is in Overwrite into a new mod (enabled by default), or with into_existing=true into an existing mod. "
                 "'only' limits it to some top-level entries (e.g. ['meshes', 'textures']); 'after'/'priority' place the mod; "
                 "dry_run=true shows the plan without moving anything. Files are moved, never deleted; replacing a file in an "
                 "existing mod needs replace_files=true.",
                 {"name": s, "into_existing": b, "only": names, "after": s, "priority": {"type": "integer"},
                  "enable": b, "replace_files": b, "dry_run": b},
                 self.create_mod_from_overwrite, ["name"], writes=True, destructive=True, main_thread=False,
                 timeout=REFRESH_WAIT + 400),
            Tool("rename_mod", "Rename a mod or separator (a separator keeps its separator status).",
                 {"name": s, "new_name": s}, self.rename_mod, ["name", "new_name"], writes=True),
            Tool("run_executable", "Start an MO2 executable by title (e.g. 'SSEEdit', 'LOOT') with the VFS. Returns at once with a run_id. Optional args replace the configured arguments.",
                 {"executable": s, "args": names, "cwd": s}, self.run_executable, ["executable"], writes=True),
            Tool("wait_for_run", f"Wait (max {MAX_WAIT} s per call) for a started program to finish; refreshes MO2 afterwards unless refresh=false.",
                 {"run_id": {"type": "integer"}, "timeout_seconds": {"type": "integer"}, "refresh": b},
                 self.wait_for_run, ["run_id"], main_thread=False, timeout=MAX_WAIT + 70),
            Tool("install_mod", "Install an archive from the downloads folder (or an absolute path). ONLY after the user approved this exact install in chat; MO2 also asks them to confirm. Installer dialogs (FOMOD) appear in MO2 for the user.",
                 {"archive": s, "name": s}, self.install_mod, ["archive"], writes=True, timeout=1800),
            Tool("download_mod", "Download a Nexus file into MO2's downloads folder through MO2's own Nexus login (needs Premium). ONLY after the user approved this exact file (mod name, file name, Nexus page) in chat. Get mod_id and file_id from the mod page's Files tab. Waits up to wait_seconds (default 300) and returns the archive name for install_mod.",
                 {"mod_id": {"type": "integer"}, "file_id": {"type": "integer"}, "wait_seconds": {"type": "integer"}},
                 self.download_mod, ["mod_id", "file_id"], writes=True, main_thread=False, timeout=MAX_WAIT + 70),
            Tool("wait_for_download", f"Wait (max {MAX_WAIT} s per call) for a download started with download_mod to finish.",
                 {"download_id": {"type": "integer"}, "timeout_seconds": {"type": "integer"}},
                 self.wait_for_download, ["download_id"], main_thread=False, timeout=MAX_WAIT + 70),
        ]
