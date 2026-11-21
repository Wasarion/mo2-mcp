"""Read the standalone LOOT's own files (%LOCALAPPDATA%/LOOT) and compare load orders.

No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import difflib
import json
import os
import re


def data_dir(local_appdata: str, game_name: str) -> str | None:
    """LOOT's folder for this game: games/<game folder>. Falls back to the folder LOOT used last."""
    games = os.path.join(local_appdata, "LOOT", "games")
    try:
        names = os.listdir(games)
    except OSError:
        return None
    exact = next((n for n in names if n.lower() == game_name.lower()), None)
    if exact:
        return os.path.join(games, exact)
    folders = [os.path.join(games, n) for n in names if os.path.isdir(os.path.join(games, n))]
    return max(folders, key=os.path.getmtime) if folders else None


def messages(game_dir: str) -> tuple[list[str], dict[str, list[str]], float] | None:
    """The messages LOOT showed last time (old_messages.json): general ones, per-plugin ones, and when it was saved."""
    path = os.path.join(game_dir, "old_messages.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    general: list[str] = []
    per_plugin: dict[str, list[str]] = {}
    for m in data.get("messages", []) if isinstance(data, dict) else []:
        if not isinstance(m, dict) or not m.get("text"):
            continue
        text = _plain(str(m["text"]))
        plugin = m.get("pluginName")
        if plugin:
            if text not in per_plugin.setdefault(str(plugin), []):
                per_plugin[str(plugin)].append(text)
        elif text not in general:
            general.append(text)
    return general, per_plugin, os.path.getmtime(path)


def _plain(text: str) -> str:
    """Markdown links [title](url) -> title (url); bold markers removed."""
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text).replace("**", "")


def latest_backup(game_dir: str) -> tuple[float, list[str]] | None:
    """LOOT saves the load order it replaces in backups/loadorder.<ms>.json before applying a sort."""
    folder = os.path.join(game_dir, "backups")
    try:
        names = [n for n in os.listdir(folder) if n.startswith("loadorder.") and n.endswith(".json")]
    except OSError:
        return None
    if not names:
        return None
    path = max((os.path.join(folder, n) for n in names), key=os.path.getmtime)
    try:
        with open(path, encoding="utf-8") as f:
            order = json.load(f).get("loadOrder", [])
    except (OSError, ValueError, AttributeError):
        return None
    return os.path.getmtime(path), [str(p) for p in order]


def moved(before: list[str], after: list[str]) -> list[dict[str, int | str]]:
    """Plugins that changed place: those outside the longest runs both orders share. Positions count from 0."""
    a = [p.lower() for p in before]
    b = [p.lower() for p in after]
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    kept: set[str] = set()
    for block in matcher.get_matching_blocks():
        kept.update(b[block.b:block.b + block.size])
    where = {p: i for i, p in enumerate(a)}
    out: list[dict[str, int | str]] = []
    for i, p in enumerate(b):
        if p not in kept and p in where:
            out.append({"plugin": after[i], "from": where[p], "to": i})
    return out


def debug_problems(local_appdata: str) -> list[str]:
    """[warning]/[error] lines of the last LOOT start (LOOTDebugLog.txt is rewritten every start)."""
    path = os.path.join(local_appdata, "LOOT", "LOOTDebugLog.txt")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    noise = ("Epic Games Launcher", "as a duplicate of the install", "No cached card exists")
    return [ln for ln in lines if re.search(r"\[(warning|error|critical)\]", ln, re.IGNORECASE)
            and not any(n in ln for n in noise)]
