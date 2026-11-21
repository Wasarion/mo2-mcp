"""Find and trim the logs of tools run through MO2: DynDOLOD, TexGen, xLODGen, xEdit, Pandora, LOOT, SKSE plugins.

No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import os
import re

# Which configured executable belongs to which log, by the executable's file name.
TOOL_EXE = {
    "dyndolod": re.compile(r"^dyndolod(x64)?\.exe$"),
    "texgen": re.compile(r"^texgen(x64)?\.exe$"),
    "xlodgen": re.compile(r"^xlodgen(x64)?\.exe$"),
    "xedit": re.compile(r"^(x|tes4|tes5|tes5vr|sse|fo3|fnv|fo4|fo4vr|sf1|enderal|enderalse)edit(64)?(quickautoclean)?\.exe$"),
}
# Log file names per tool (lower case); debug logs are left out on purpose: they are huge and rarely needed.
TOOL_LOG = {
    "dyndolod": re.compile(r"^dyndolod_\w+_log\.txt$"),
    "texgen": re.compile(r"^texgen_\w+_log\.txt$"),
    "xlodgen": re.compile(r"^\w*lodgen_log\.txt$"),
    "xedit": re.compile(r"^\w*edit\w*_log\.txt$"),
}
SESSION = re.compile(r"\bstarting session \d{4}-\d\d-\d\d")
PROBLEM = re.compile(
    r"\b(warning|warn|error|errors|exception|failed|failure|not found|missing|cannot|can't|access violation)\b"
    r"|\[(w|e|c|warning|error|critical)\]", re.IGNORECASE)
# xEdit lines worth seeing after a run: what Quick Auto Clean did, and what was saved.
XEDIT_HIGHLIGHT = re.compile(
    r"^\[(Undeleting and Disabling References|Removing \"Identical to Master\" records|Removing Deleted Navmeshes)"
    r".* done\]|^\[[\d:]+\] Saving: |^\s+(itm|udr|nav\w*): \d+", re.IGNORECASE)


def tool_folders(executables: list[tuple[str, str]], kind: str) -> list[str]:
    """Folders of the configured executables (title, binary path) that belong to this tool."""
    out: list[str] = []
    pattern = TOOL_EXE[kind]
    for _, binary in executables:
        if binary and pattern.match(os.path.basename(binary).lower()):
            folder = os.path.normpath(os.path.dirname(binary))
            if folder not in out:
                out.append(folder)
    return out


def find_tool_log(folders: list[str], kind: str) -> str | None:
    """The newest log of this tool in its folders or their Logs subfolder."""
    pattern = TOOL_LOG[kind]
    found: list[str] = []
    for folder in folders:
        for where in (folder, os.path.join(folder, "Logs")):
            try:
                names = os.listdir(where)
            except OSError:
                continue
            found += [os.path.join(where, n) for n in names if pattern.match(n.lower()) and "debug" not in n.lower()]
    return max(found, key=os.path.getmtime) if found else None


def last_session(lines: list[str]) -> tuple[list[str], int]:
    """Lines from the last 'starting session' line on (xEdit-based tools append sessions), and how many sessions."""
    starts = [i for i, ln in enumerate(lines) if SESSION.search(ln)]
    if not starts:
        return lines, 0
    return lines[starts[-1]:], len(starts)


def problems(lines: list[str]) -> list[str]:
    return [ln for ln in lines if PROBLEM.search(ln)]


def xedit_highlights(lines: list[str]) -> list[str]:
    return [ln.strip() for ln in lines if XEDIT_HIGHLIGHT.search(ln)]


def dyndolod_summary(folders: list[str]) -> tuple[str, list[str]] | None:
    """DynDOLOD's own summary of log messages (Summary/DynDOLOD_Summary_*.html): the index and the topics."""
    for folder in folders:
        summary = os.path.join(folder, "Summary")
        try:
            names = os.listdir(summary)
        except OSError:
            continue
        topics = sorted(n[len("DynDOLOD_Summary_"):-5] for n in names
                        if n.startswith("DynDOLOD_Summary_") and n.endswith(".html")
                        and n not in ("DynDOLOD_Summary_Index.html", "DynDOLOD_Summary_Links.html"))
        index = os.path.join(summary, "DynDOLOD_Summary_Index.html")
        if os.path.isfile(index):
            return index, topics
    return None


def bugreport(folders: list[str]) -> str | None:
    """bugreport.txt, which DynDOLOD/TexGen/xEdit write next to themselves after a crash or error."""
    found = [os.path.join(f, "bugreport.txt") for f in folders if os.path.isfile(os.path.join(f, "bugreport.txt"))]
    return max(found, key=os.path.getmtime) if found else None
