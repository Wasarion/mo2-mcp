"""SKSE helpers: read SKSE's own log, decode plugin versions and read a DLL's file version.

No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

# SKSE 2.3 writes one result line per DLL, for example:
#   plugin EngineFixes.dll (00000001 EngineFixes 07000000) loaded correctly (handle 12)
#   plugin msdia140.dll (00000000  00000000) no version data 0 (handle 0)
# The part in brackets is: interface version, the plugin's own name, its packed version.
_RESULT = re.compile(r"^plugin (?P<dll>.+?\.dll) \((?P<info>[0-9a-f]{8}.*?[0-9a-f]{8})\) (?P<result>.+)$", re.IGNORECASE)
_INFO = re.compile(r"^[0-9a-f]{8}\s*(?P<name>.*?)\s*(?P<version>[0-9a-f]{8})$", re.IGNORECASE)
_CHECKING = re.compile(r"^checking plugin (?P<dll>.+?\.dll)\s*$", re.IGNORECASE)
_COULDNT = re.compile(r"couldn't load plugin (?P<dll>.+?\.dll)", re.IGNORECASE)
_SKSE_VERSION = re.compile(r"SKSE64 runtime: initialize \(version = (?P<version>[\d.]+)")
_HANDLE = re.compile(r"\s*\(handle \d+\)\s*$")


@dataclass
class LogEntry:
    dll: str
    loaded: bool
    result: str
    name: str = ""
    version: str = ""

    @property
    def helper(self) -> bool:
        """SKSE found no plugin version data: a helper library (e.g. msdia140.dll) that SKSE skips on purpose."""
        return not self.loaded and self.result.lower().startswith("no version data")


@dataclass
class SkseLog:
    skse_version: str
    entries: dict[str, LogEntry]  # keyed by lower-case DLL name


def plugin_version(raw: int) -> str:
    """SKSE plugin versions are usually packed as major<<24 | minor<<16 | patch<<4 | build."""
    if raw >> 24:
        major, minor, patch, build = raw >> 24, (raw >> 16) & 0xFF, (raw >> 4) & 0xFFF, raw & 0xF
        return f"{major}.{minor}.{patch}" + (f".{build}" if build else "")
    return str(raw)


def parse_skse_log(text: str) -> SkseLog:
    entries: dict[str, LogEntry] = {}
    skse_version = ""
    for line in text.splitlines():
        line = line.strip()
        m = _SKSE_VERSION.search(line)
        if m:
            skse_version = m["version"]
            continue
        m = _CHECKING.match(line)
        if m:
            entries.setdefault(m["dll"].lower(), LogEntry(m["dll"], False, "checked, but no result in the log"))
            continue
        m = _RESULT.match(line)
        if m:
            name = version = ""
            info = _INFO.match(m["info"].strip())
            if info:
                name = info["name"]
                raw = int(info["version"], 16)
                version = f"{plugin_version(raw)} (0x{raw:08X})" if raw else ""
            result = _HANDLE.sub("", m["result"]).strip()
            entries[m["dll"].lower()] = LogEntry(m["dll"], result.lower().startswith("loaded correctly"), result, name, version)
            continue
        m = _COULDNT.search(line)
        if m:
            entries[m["dll"].lower()] = LogEntry(m["dll"], False, line)
    return SkseLog(skse_version, entries)


def dll_file_version(path: str) -> str | None:
    """The file version from a DLL's version resource (Windows only)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    version = ctypes.WinDLL("version")  # type: ignore[attr-defined]
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, buffer):
        return None
    info = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(info), ctypes.byref(length)) or not info.value:
        return None
    # VS_FIXEDFILEINFO: signature, struct version, file version MS, file version LS, ...
    fixed = ctypes.cast(info, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
    ms, ls = fixed[2], fixed[3]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
