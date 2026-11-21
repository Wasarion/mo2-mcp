"""Read Skyrim SE plugin files (.esp/.esm/.esl) directly: header, masters and record counts.

Only record headers are read (24 bytes each); record contents are skipped, so even large
plugins are read quickly. No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import mmap
import os
import struct
from dataclasses import dataclass, field

FLAG_MASTER = 0x1
FLAG_LIGHT = 0x200
MAX_LIGHT_RECORDS = 4096  # object IDs 0x000-0xFFF (header version 1.71), or 0x800-0xFFF (2048) before that


@dataclass
class PluginFile:
    name: str
    flags: int
    form_version: float          # HEDR version: 1.71 lets light plugins use object IDs from 0x000
    masters: list[str]
    records: int = 0             # every record except the TES4 header
    new_records: int = 0         # records this plugin creates (not overrides of a master's)
    min_new_id: int | None = None
    max_new_id: int | None = None
    new_cells: int = 0           # new CELL records
    new_worldspaces: int = 0     # new WRLD records
    notes: list[str] = field(default_factory=list)

    @property
    def master_flag(self) -> bool:
        return bool(self.flags & FLAG_MASTER)

    @property
    def light(self) -> bool:
        return bool(self.flags & FLAG_LIGHT) or self.name.lower().endswith(".esl")

    @property
    def light_id_start(self) -> int:
        return 0x000 if self.form_version >= 1.705 else 0x800


def read_plugin(path: str) -> PluginFile:
    name = os.path.basename(path)
    with open(path, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        if size < 24:
            raise ValueError(f"{name} is too small to be a plugin.")
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
            if data[0:4] != b"TES4":
                raise ValueError(f"{name} is not a Skyrim plugin (no TES4 header).")
            header_size, flags = struct.unpack_from("<II", data, 4)
            plugin = PluginFile(name, flags, 0.0, [])
            _read_header(data, 24, 24 + header_size, plugin)
            _count_records(data, 24 + header_size, size, plugin)
    return plugin


def _read_header(data: mmap.mmap, start: int, end: int, plugin: PluginFile) -> None:
    pos = start
    big_size = None
    while pos + 6 <= end:
        kind = bytes(data[pos:pos + 4])
        (sub_size,) = struct.unpack_from("<H", data, pos + 4)
        pos += 6
        if big_size is not None:  # an XXXX subrecord gave the real size of this one
            sub_size, big_size = big_size, None
        if kind == b"XXXX":
            (big_size,) = struct.unpack_from("<I", data, pos)
        elif kind == b"HEDR" and sub_size >= 12:
            plugin.form_version = round(struct.unpack_from("<f", data, pos)[0], 3)
        elif kind == b"MAST":
            plugin.masters.append(bytes(data[pos:pos + sub_size]).split(b"\0", 1)[0].decode("cp1252", "replace"))
        pos += sub_size


def _count_records(data: mmap.mmap, pos: int, end: int, plugin: PluginFile) -> None:
    own_index = len(plugin.masters)  # a FormID whose top byte is this index is a new record
    while pos + 24 <= end:
        kind = bytes(data[pos:pos + 4])
        (size,) = struct.unpack_from("<I", data, pos + 4)
        if kind == b"GRUP":
            pos += 24  # step into the group; its records follow its header
            continue
        (form_id,) = struct.unpack_from("<I", data, pos + 12)
        plugin.records += 1
        if form_id >> 24 >= own_index:
            object_id = form_id & 0xFFFFFF
            plugin.new_records += 1
            plugin.min_new_id = object_id if plugin.min_new_id is None else min(plugin.min_new_id, object_id)
            plugin.max_new_id = object_id if plugin.max_new_id is None else max(plugin.max_new_id, object_id)
            if kind == b"CELL":
                plugin.new_cells += 1
            elif kind == b"WRLD":
                plugin.new_worldspaces += 1
        pos += 24 + size
    if pos != end:
        plugin.notes.append("The file ends in the middle of a record; it may be damaged.")


def light_verdict(plugin: PluginFile) -> tuple[str, str]:
    """(code, explanation) for whether this plugin could be a light plugin."""
    if plugin.light:
        return "already_light", "Already a light plugin."
    if plugin.new_records == 0:
        return "flag_as_is", "Adds no new records, so it can be flagged light as is."
    if plugin.new_records > MAX_LIGHT_RECORDS:
        return "too_many", f"Adds {plugin.new_records} new records; a light plugin holds at most {MAX_LIGHT_RECORDS}."
    caution = ""
    if plugin.new_cells or plugin.new_worldspaces:
        caution = (f" Caution: it adds {plugin.new_cells} new cell(s) and {plugin.new_worldspaces} new worldspace(s);"
                   " check those in xEdit before flagging it light.")
    assert plugin.min_new_id is not None and plugin.max_new_id is not None
    if plugin.min_new_id >= plugin.light_id_start and plugin.max_new_id <= 0xFFF:
        return "flag_as_is", "All new FormIDs are already in the light range, so it can be flagged light as is." + caution
    if plugin.max_new_id <= 0xFFF:  # IDs below 0x800 in a plugin with header version 1.70
        return ("needs_header_171",
                "Its new FormIDs fit 0x000-0xFFF, which a light plugin may only use with header version 1.71 (game "
                "1.6.1130 or newer). Raising the header version in xEdit changes no FormIDs." + caution)
    return ("needs_compacting",
            f"Its new FormIDs (up to 0x{plugin.max_new_id:06X}) are outside the light range, so they would have to be "
            "compacted in xEdit first. That changes FormIDs and breaks plugins, INI files (SPID, KID…), facegen and saves "
            "that refer to them." + caution)
