"""The MO2 tools exposed over MCP. Handlers run on MO2's GUI thread unless marked otherwise."""

from __future__ import annotations

import os
from typing import Any, Callable

import mobase
from PyQt6.QtCore import QSettings

from .mcp import Tool, ToolError
from .procs import RunTracker

MAX_WAIT = 600  # seconds one wait_for_run call may block


def _flag(state: Any, flag: Any) -> bool:
    return (int(state) & int(flag)) != 0


class Mo2Tools:
    def __init__(
        self,
        organizer: mobase.IOrganizer,
        runs: RunTracker,
        confirm_install: Callable[[str, str], bool],
        invoke: Callable[[Callable[[], Any], float], Any],
    ):
        self.org = organizer
        self.runs = runs
        self.confirm_install = confirm_install
        self.invoke = invoke  # run something on the GUI thread (for worker-thread tools)

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
        files: list[str] = []
        for root, _, fnames in os.walk(path):
            for f in fnames:
                files.append(os.path.relpath(os.path.join(root, f), path).replace("\\", "/"))
        files = [f for f in files if f.lower() != "meta.ini"]
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
        }
        if args.get("list_files"):
            limit = int(args.get("max_files", 300))
            info["files"] = sorted(files)[:limit]
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
        self.org.refresh(True)
        return "Refresh started. MO2 rebuilds the mod and plugin lists in the background; wait a few seconds before reading them."

    def run_executable(self, args: dict[str, Any]) -> Any:
        exe = str(args["executable"])
        exe_args = [str(a) for a in args.get("args", [])]
        known = {e["title"].lower(): e["title"] for e in self.list_executables({})}
        title = known.get(exe.lower(), exe)
        if title == exe and not os.path.isabs(exe):
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
            self.invoke(lambda: self.org.refresh(True), 60)
            result["refreshed"] = True
        elif run.running:
            result["note"] = "Still running; call wait_for_run again."
        return result

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
            Tool("refresh", "Refresh MO2 (like F5), e.g. after a tool wrote files.",
                 {}, self.refresh, writes=True),
            Tool("run_executable", "Start an MO2 executable by title (e.g. 'SSEEdit', 'LOOT') with the VFS. Returns at once with a run_id. Optional args replace the configured arguments.",
                 {"executable": s, "args": names, "cwd": s}, self.run_executable, ["executable"], writes=True),
            Tool("wait_for_run", f"Wait (max {MAX_WAIT} s per call) for a started program to finish; refreshes MO2 afterwards unless refresh=false.",
                 {"run_id": {"type": "integer"}, "timeout_seconds": {"type": "integer"}, "refresh": b},
                 self.wait_for_run, ["run_id"], main_thread=False, timeout=MAX_WAIT + 70),
            Tool("install_mod", "Install an archive from the downloads folder (or an absolute path). ONLY after the user approved this exact install in chat; MO2 also asks them to confirm. Installer dialogs (FOMOD) appear in MO2 for the user.",
                 {"archive": s, "name": s}, self.install_mod, ["archive"], writes=True, timeout=1800),
        ]
