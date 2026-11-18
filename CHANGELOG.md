# Changelog

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
