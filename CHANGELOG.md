# Changelog

## 0.12.0

- New tool `loot_sort` (closes #25): sorts with the standalone LOOT configured in MO2's executables (binary `LOOT.exe`, or a title you give), never MO2's built-in sort. It starts LOOT through the VFS with the configured arguments plus LOOT's documented `--auto-sort` option (sort, apply, quit), waits, refreshes MO2 and compares the load order before and after (new module `loot.py`): only the plugins that changed place are listed. It adds LOOT's messages for enabled plugins (from LOOT's own `old_messages.json`, links kept readable) and warnings or errors from `LOOTDebugLog.txt`. `dry_run` sorts nothing and shows LOOT's last messages and what its last sort moved (from LOOT's backup of the previous order). Changing the load order counts as a write, so it is refused while another program started by the plugin runs.

## 0.11.0

- `read_log` reads the logs of tools run through MO2 (closes #24, new module `toollogs.py`): `dyndolod`, `texgen`, `xlodgen` and `xedit` (found next to the executables configured in MO2, or in their `Logs` folder; debug logs skipped), `pandora` (`Engine.log` in the enabled Pandora output mod), `loot` (`LOOTDebugLog.txt`) and `skse` with `name` for any SKSE plugin's log in My Games (without a name it lists them). xEdit-based tools append every run to one file, so only the last session is shown unless `session=false`. For xEdit it also lists what Quick Auto Clean removed and saved; for DynDOLOD it points to DynDOLOD's own summary of log messages with its topics, and for all of these to a `bugreport.txt` if one exists. New option `problems_only` keeps warnings and errors.

## 0.10.0

- New tool `check_community_shaders` (closes #23): which mod provides `CommunityShaders.dll` and which other mods carry a copy, every `Shaders/Features/*.ini` in the enabled mods with its `[Info] Version` and the winning mod, and a problem when a separate feature mod overrides the version that comes with the core (a common leftover after moving to the all-in-one download). From `CommunityShaders.log` (new module `cshaders.py`, matching the messages in Community Shaders' own source): the core version and each feature's status at the last game start (loaded, not installed, disabled at boot, old version, obsolete, unknown), plus its warnings and errors. Also lists shader cache folders and notes when they are older than the installed DLL. `problems_only` keeps the features that need a look.

## 0.9.0

- New tool `check_outputs` (closes #22): is generated output out of date? Output mods are found by name (containing "Output", or the names given) and recognized by their content as Pandora, PGPatcher, xLODGen, TexGen or DynDOLOD output (new module `outputs.py`). For each: when it was made (its newest file), the enabled mods with files that matter to that tool and are newer than it (with a count and examples; plugins count for xLODGen and DynDOLOD only when they hold worldspace or LOD object records, which `plugin_header`'s reader now also reports), whether the profile's mod list or load order was saved since, masters of its plugins that are no longer enabled, the plugins loading after them, and for Pandora the patches ticked in its last run compared with the ones installed now. A later step's output never makes an earlier step stale (TexGen output newer than PGPatcher's is fine), and files written within five minutes of the output count as the same run. It compares file times only and never reruns anything.

## 0.8.0

- New tool `plugin_header` (closes #19): reads plugin files directly (new module `espm.py`, record headers only, so a whole load order takes seconds) and reports flags, header version, masters, record and new-record counts, the new FormID range and a light-plugin verdict: `already_light`, `flag_as_is` (no new records, or all in the light range), `needs_header_171`, `needs_compacting` (with the enabled plugins that use it as a master) or `too_many`, plus a caution for new cells or worldspaces. Without names it checks every enabled full plugin except Bethesda's own and counts full plugin slots; `candidates_only` keeps the ones that need no FormID changes. It never changes a file.

## 0.7.0

- New tool `list_skse_plugins` (closes #18): every `SKSE/Plugins/*.dll` in the mods folder and the game's Data folder, with its mod and whether that mod is enabled, whether another mod's copy wins, and whether it loaded in the last game start. The last part comes from SKSE's own `skse64.log` (in My Games), which SKSE 2.3 writes per DLL with the plugin's name and version or the reason it was not loaded. Also shows each DLL's file version and lists DLLs in the log that no mod provides. Filters: text, `enabled_only`, `problems_only`.

## 0.6.0

- New tool `list_notifications` (closes #4, with `read_log` from 0.2.0): MO2's notifications, the list behind the warning-triangle button, with each problem's details and whether MO2 offers a guided fix. MO2 gives plugins no access to that list, so the tool opens MO2's own notifications window, reads it and closes it again; you may see it flash. It does nothing when MO2 counts no notifications, and refuses while another dialog is open or MO2 is locked.

## 0.5.0

- New tools `list_profiles` and `switch_profile` (closes #3). MO2's plugin API has no way to change profiles, so `switch_profile` selects the profile in MO2's own profile box, which runs MO2's normal switch: it saves the current lists, activates the profile and refreshes. The `<Manage...>` entry is never selected, and the switch is refused while the box is locked (MO2 locks it while a program it started is running) or while a program started with `run_executable` is running.

## 0.4.0

- New tool `create_mod_from_overwrite` (closes #1): moves what is in Overwrite into a new mod (enabled and optionally placed with `after`/`priority`) or, with `into_existing=true`, into an existing mod such as an xEdit output mod. `only` moves just some top-level folders, `dry_run` lists what would move without moving anything, and replacing a file in an existing mod needs `replace_files=true`. Files are moved, never deleted; folders the move leaves empty are removed. Refused while a program started with `run_executable` is still running.

## 0.3.1

- `wait_for_download` finds a finished download by its `.meta` file instead of MO2's download id (#13).

## 0.3.0

- New tools `download_mod` and `wait_for_download`: download a Nexus file through MO2's own Nexus login (#12).

## 0.2.1

- `get_mod` leaves out files and folders MO2 hides (`.mohidden`), counts them in `hidden_by_mo2`, and lists them under `hidden_files` with `list_files`. `get_mod_conflicts` also skips hidden folders, not only hidden files.
- A wrong, missing or unknown argument now comes back as a tool error (`isError`) the AI can read and fix, instead of a protocol error. An unknown tool name is still a protocol error, as MCP requires.
- Both ideas come from houseCARL 2.2.0.

## 0.2.0

- New tools: `create_separator`, `rename_mod`, `get_mod_conflicts`, `read_log` (closes #2, #5; #4 in part).
- `refresh` and `wait_for_run` now wait until MO2 has finished refreshing.
- Approach for these follows Antiarc123's MCP - MO2 (credited in the README).

## 0.1.0

- First release: 15 tools, PowerShell stdio bridge, token/Host/Origin checks, install confirmation dialog, end-to-end test and CI.
