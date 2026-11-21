"""Read Crash Logger SSE/AE crash logs (My Games/<game>/SKSE/crash-*.log).

No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EXCEPTION = re.compile(r'^Unhandled exception "([^"]+)" at 0x[0-9A-Fa-f]+ (.+?)\+([0-9A-Fa-f]+)')
_FRAME = re.compile(r"^\s*\[\s*(\d+)\]\[([PS])\]\s+0x[0-9A-Fa-f]+\s+(.+?)\+([0-9A-Fa-f]+)(.*)$")
_SOURCE = re.compile(r"([\w.\-]+\.(?:cpp|cxx|cc|c|hpp|hxx|h)):(\d+)")
_QUOTED = re.compile(r'"([^"]+)"')
_SECTION = re.compile(r"^([A-Z][A-Z ]*[A-Z])(?: \(.*\))?:$")
GAME_EXE = {"skyrimse.exe", "skyrimvr.exe", "skyrim.exe"}
# Windows, runtime, driver and overlay modules: never a mod's fault on their own.
SYSTEM = re.compile(r"^(kernel32|kernelbase|ntdll|ucrtbase|msvcp\d+.*|vcruntime\d+.*|user32|win32u|gdi32.*|combase|"
                    r"d3d11|d3d12|dxgi|d3dcompiler.*|nv\w+|amd\w+|atio\w+|igd\w+|gameoverlayrenderer64|"
                    r"steam_api64|xinput.*|x3daudio.*|xaudio.*|dinput8|dbghelp|ws2_32|rpcrt4|sechost|bcrypt.*|"
                    r"advapi32|shell32|ole32|oleaut32|msvcrt|cfgmgr32|dwmapi|uxtheme|windows\..*)\.(dll|exe)$",
                    re.IGNORECASE)


@dataclass
class Frame:
    index: int
    probable: bool          # [P]: from the real call stack; [S]: found by scanning the stack (less certain)
    module: str
    source: str | None      # file:line from the module's debug symbols, when Crash Logger had them


@dataclass
class CrashLog:
    time: str | None = None
    game: str | None = None
    logger: str | None = None
    exception: str | None = None
    exception_module: str | None = None
    role: str | None = None
    frames: list[Frame] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)   # lines of POSSIBLE RELEVANT OBJECTS
    plugins: list[str] = field(default_factory=list)   # plugin files named in those objects
    files: list[str] = field(default_factory=list)     # meshes/textures named in those objects (Data-relative)


def parse(text: str) -> CrashLog:
    log = CrashLog()
    section = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if line.startswith("CRASH TIME:"):
            log.time = line.split(":", 1)[1].strip()
        elif log.game is None and line.startswith(("Skyrim ", "Fallout ")):
            log.game = stripped
        elif log.logger is None and line.startswith("CrashLogger"):
            log.logger = stripped
        elif m := _EXCEPTION.match(line):
            log.exception, log.exception_module = m.group(1), m.group(2).strip()
        elif stripped.startswith("Likely Role:"):
            log.role = stripped.split(":", 1)[1].strip()
        if m := _SECTION.match(line):
            section = m.group(1)
            continue
        if section in ("CALL STACK", "PROBABLE CALL STACK"):
            if m := _FRAME.match(line):
                src = _SOURCE.search(m.group(5))
                log.frames.append(Frame(int(m.group(1)), m.group(2) == "P", m.group(3).strip(),
                                        f"{src.group(1)}:{src.group(2)}" if src else None))
        elif section == "POSSIBLE RELEVANT OBJECTS" and stripped:
            log.objects.append(stripped)
            for q in _QUOTED.findall(stripped):
                low = q.lower()
                if low.endswith((".esp", ".esm", ".esl")):
                    if q not in log.plugins:
                        log.plugins.append(q)
                elif low.endswith((".nif", ".dds", ".hkx", ".tri", ".bto", ".btr")):
                    rel = q.replace("\\", "/").lstrip("/")
                    top = "textures/" if low.endswith(".dds") else "meshes/"
                    if not rel.lower().startswith(("meshes/", "textures/")):
                        rel = top + rel
                    if rel not in log.files:
                        log.files.append(rel)
    return log


def is_game(module: str) -> bool:
    return module.lower() in GAME_EXE


def is_system(module: str) -> bool:
    return SYSTEM.match(module) is not None
