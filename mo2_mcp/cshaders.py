"""Read Community Shaders' own files: feature .ini versions and CommunityShaders.log.

The log lines matched here come from Community Shaders' source (src/Feature.cpp, src/FeatureIssues.cpp).
No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_LINE = re.compile(r"^\[[\d:.]+\]\s*\[\s*\d+\s*\]\s*\[(\w)\]\s?(.*)$")
_VERSION = re.compile(r"^Community ?Shaders v?(\d[\w.\-]*)")
_LOADED = re.compile(r"^(\S+)\.ini (\S+) successfully loaded$")
_FAILED = re.compile(r"^(\S+)\.ini failed to load, feature disabled$")
_AT_BOOT = re.compile(r"^Feature '(.+)' is disabled at boot\.$")
_OBSOLETE = re.compile(r"^Found (?:orphaned )?obsolete feature INI: (\S+) version (\S+)$")
_UNKNOWN = re.compile(r"^Found orphaned unknown feature INI: (\S+)$")
_FEATURE_ISSUE = re.compile(r"^(\S+) (\S+) is (an old feature version|too old|an unknown feature|an obsolete feature)")


@dataclass
class CsLog:
    version: str | None = None
    # feature short name (lower case) -> (status, detail)
    features: dict[str, tuple[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)  # [W], [E] and [C] lines, without the time stamp
    names: dict[str, str] = field(default_factory=dict)  # lower case -> name as written


def parse_cs_log(text: str) -> CsLog:
    log = CsLog()

    def put(name: str, status: str, detail: str = "") -> None:
        log.names.setdefault(name.lower(), name)
        log.features[name.lower()] = (status, detail)

    for raw in text.splitlines():
        m = _LINE.match(raw)
        level, msg = (m.group(1), m.group(2).strip()) if m else ("I", raw.strip())
        if log.version is None:
            v = _VERSION.match(msg)
            if v:
                log.version = v.group(1).rstrip(".")
        if level in ("W", "E", "C") and msg not in log.warnings:
            log.warnings.append(f"[{level}] {msg}")
        if m := _LOADED.match(msg):
            put(m.group(1), "loaded", m.group(2))
        elif m := _FAILED.match(msg):
            put(m.group(1), "not installed", "no .ini found")
        elif m := _AT_BOOT.match(msg):
            put(m.group(1), "disabled at boot", "turned off in Community Shaders' menu")
        elif m := _OBSOLETE.match(msg):
            put(m.group(1), "obsolete", f"version {m.group(2)} is a feature Community Shaders removed")
        elif m := _UNKNOWN.match(msg):
            put(m.group(1), "unknown", "not a feature of this Community Shaders version")
        elif level in ("W", "E") and (m := _FEATURE_ISSUE.match(msg)):
            put(m.group(1), "not loaded", msg)
    return log


def ini_version(text: str) -> str | None:
    """[Info] Version = 1-3-0 from a feature .ini."""
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
        elif section == "info" and "=" in line:
            key, value = line.split("=", 1)
            if key.strip().lower() == "version":
                return value.strip()
    return None
