# Changelog

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
