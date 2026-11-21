# Changelog

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
