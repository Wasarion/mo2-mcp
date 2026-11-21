"""Is generated output out of date? Recognize output mods (Pandora, PGPatcher, xLODGen, TexGen, DynDOLOD)
and find the files in other mods that changed after the output was made.

No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import json
import os
import re
import struct

from .espm import read_plugin

# Order in which the Step guide runs the generators. A later stage's output never makes an earlier one stale
# (TexGen output is new after PGPatcher ran, and that is fine); Pandora stands apart.
STAGE = {"pgpatcher": 0, "xlodgen": 1, "texgen": 2, "dyndolod": 3, "pandora": 10}
LABEL = {"pandora": "Pandora", "pgpatcher": "PGPatcher", "xlodgen": "xLODGen (terrain LOD)",
         "texgen": "TexGen", "dyndolod": "DynDOLOD"}
WATCHES = {
    "pandora": "behavior and character files under meshes/actors (not plain animations), FNIS lists, "
               "Nemesis and Pandora patches",
    "pgpatcher": "meshes, and parallax, complex material and PBR textures",
    "xlodgen": "plugins with worldspace or object records, landscape and terrain textures, terrain meshes and LOD files",
    "texgen": "meshes and textures of architecture, landscape, plants, trees and LOD",
    "dyndolod": "plugins with worldspace or object records, LOD meshes and textures, terrain files and DynDOLOD rules",
}
PLUGIN_EXT = (".esp", ".esm", ".esl")
LOD_KINDS = ("xlodgen", "dyndolod")
# Top-level record groups that LOD tools read: worldspaces (exterior cells, references, landscape) and base objects
# that can have LOD. A plugin with only quests, interiors, spells... does not change LOD.
LOD_GROUPS = {"WRLD", "STAT", "TREE", "SCOL", "MSTT", "FLOR", "LTEX", "TXST"}
GRACE = 300  # seconds after an output was made in which newer files are taken as part of the same run
_LOD = re.compile(r"[/_]lod[/_.]")
_FNIS_LIST = re.compile(r"fnis_.*_list\.txt$")
_PG_TEXTURE = re.compile(r"(_p|_m|_em|_rmaos|_cnr)\.dds$")
_TEXGEN_DIRS = {"architecture", "landscape", "lod", "plants", "trees", "terrain", "mountains", "rocks"}
GENERATED = {"occlusion.esp"}  # made by xLODGen/DynDOLOD from the load order itself


def _has_dir(root: str, *names: str) -> bool:
    path = _find(root, *names)
    return path is not None and os.path.isdir(path)


def detect_kind(root: str) -> str | None:
    """Which generator made this output mod, judged by its content."""
    try:
        top = [e.lower() for e in os.listdir(root)]
    except OSError:
        return None
    if any(n.startswith("dyndolod") and n.endswith(PLUGIN_EXT) for n in top):
        return "dyndolod"
    if "pandora_engine" in top or ("engine.log" in top and "meshes" in top):
        return "pandora"
    if any(n.startswith("pgpatcher") for n in top):
        return "pgpatcher"
    if _has_dir(root, "meshes", "terrain"):
        return "xlodgen"
    if _has_dir(root, "textures", "terrain") or _has_dir(root, "textures", "lod"):
        return "texgen"
    return None


def relevant(kind: str, rel: str) -> bool:
    """Would a change to this file (relative path, '/') matter to this generator? Plugins found here still need
    plugin_matters() for the LOD tools."""
    rel = rel.lower()
    top, _, rest = rel.partition("/")
    ext = os.path.splitext(rel)[1]
    if rest.startswith("terrain/heightmaps/"):  # Community Shaders' terrain shadow maps, not LOD
        return False
    parts = rel.split("/")
    lod_or_terrain = top in ("meshes", "textures") and (_LOD.search(rel) is not None or rest.startswith("terrain/"))
    root_plugin = len(parts) == 1 and ext in PLUGIN_EXT and rel not in GENERATED
    if kind == "pandora":
        if top in ("nemesis_engine", "pandora_engine"):
            return True
        if not rel.startswith("meshes/actors/"):
            return False
        if _FNIS_LIST.search(parts[-1]):
            return True
        return ext == ".hkx" and "/animations/" not in rel
    if kind == "pgpatcher":
        if lod_or_terrain:
            return False
        return (top == "meshes" and ext == ".nif") or (top == "textures" and ext == ".dds" and (
            rest.startswith("pbr/") or _PG_TEXTURE.search(rel) is not None))
    if kind == "texgen":
        return ((top == "meshes" and ext == ".nif") or (top == "textures" and ext == ".dds")) and (
            lod_or_terrain or any(p in _TEXGEN_DIRS for p in parts[1:-1]))
    if kind == "xlodgen":
        return root_plugin or lod_or_terrain or rel.startswith("textures/landscape/")
    if kind == "dyndolod":
        return root_plugin or lod_or_terrain or top == "dyndolod"
    return False


def plugin_matters(path: str) -> bool:
    """Does this plugin hold records LOD tools read? Unreadable plugins count as mattering."""
    try:
        return bool(read_plugin(path).top_groups & LOD_GROUPS)
    except (OSError, ValueError, struct.error):
        return True


def _file_time(st: os.stat_result) -> float:
    # A file extracted from an archive keeps its old modified time, but gets a new creation time on Windows.
    return max(st.st_mtime, getattr(st, "st_birthtime", 0.0))


def changed_files(root: str, since: float) -> list[tuple[str, float]]:
    """Files under root (relative, '/') added or changed after `since`.
    MO2's hidden files (*.mohidden) and meta.ini are skipped."""
    out: list[tuple[str, float]] = []
    stack = [("", root)]
    while stack:
        rel, path = stack.pop()
        try:
            it = os.scandir(path)
        except OSError:
            continue
        with it:
            for entry in it:
                name = entry.name
                if name.lower().endswith(".mohidden"):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((rel + name + "/", entry.path))
                        continue
                    if not rel and name.lower() == "meta.ini":
                        continue
                    t = _file_time(entry.stat(follow_symlinks=False))
                except OSError:
                    continue
                if t > since:
                    out.append((rel + name, t))
    return out


def made_time(root: str) -> float | None:
    """When an output was made: the modified time of its newest file (meta.ini and hidden files left out)."""
    newest = None
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.lower().endswith(".mohidden")]
        for f in files:
            if f.lower().endswith(".mohidden") or (dirpath == root and f.lower() == "meta.ini"):
                continue
            try:
                t = os.path.getmtime(os.path.join(dirpath, f))
            except OSError:
                continue
            newest = t if newest is None or t > newest else newest
    return newest


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def behavior_patches(root: str) -> dict[str, str]:
    """Nemesis-style (Nemesis_Engine/mod/<code>/info.ini) and Pandora-style (Pandora_Engine/mod/<code>/info.xml)
    patches a mod provides: code -> display name. Folders without one of those files are engine data, not patches."""
    out: dict[str, str] = {}
    for engine, info, pattern in (("nemesis_engine", "info.ini", r"^\s*name\s*=\s*(.+?)\s*$"),
                                  ("pandora_engine", "info.xml", r"<name>\s*(.*?)\s*</name>")):
        mod_dir = _find(root, engine, "mod")
        if mod_dir is None:
            continue
        for code in sorted(os.listdir(mod_dir)):
            info_path = _find(os.path.join(mod_dir, code), info)
            if info_path is None or code.lower() == "pandora":  # Pandora Base is always active
                continue
            m = re.search(pattern, _read_text(info_path), re.MULTILINE)
            out[code.lower()] = m.group(1) if m else code
    return out


def pandora_last_run(root: str) -> list[str] | None:
    """Codes of the patches that were ticked when Pandora last ran (Pandora_Engine/ActiveMods.json)."""
    path = _find(root, "pandora_engine", "activemods.json")
    if path is None:
        return None
    try:
        data = json.loads(_read_text(path))
    except ValueError:
        return None
    return sorted(str(x.get("code", "")).lower() for x in data if isinstance(x, dict) and x.get("active"))


def _find(root: str, *names: str) -> str | None:
    """root/names... matched case-insensitively; a file or a folder."""
    path = root
    for name in names:
        try:
            match = next((e for e in os.listdir(path) if e.lower() == name.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        path = os.path.join(path, match)
    return path
