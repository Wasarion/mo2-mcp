# mo2-mcp

**Let an AI assistant work in your Mod Organizer 2 for you.**

mo2-mcp is a small plugin for [Mod Organizer 2](https://github.com/ModOrganizer2/modorganizer) (MO2). It lets an AI assistant that speaks [MCP](https://modelcontextprotocol.io), such as the Claude desktop app, see and use your running MO2 directly, instead of you clicking through it or sending screenshots.

You can ask things like:

- "Which mods overwrite files from SMIM, and which win over it?"
- "Turn on everything under the Extenders separator and put Address Library right after the separator."
- "Run xEdit Quick Auto Clean, wait until it finishes, then move what it wrote in Overwrite into the xEdit_Output mod."
- "DynDOLOD is done: make a mod called DynDOLOD Output from Overwrite and put it under my LOD separator."
- "Did all my SKSE plugins load the last time I started the game?"
- "I added a few mods since yesterday. Do I need to rerun Pandora, TexGen or DynDOLOD?"
- "How many full plugin slots am I using, and which plugins could be flagged light without changing FormIDs?"
- "Did every Community Shaders feature load, and is an old feature mod overriding the AIO?"
- "Sort with LOOT and tell me what moved."
- "Switch to my Mod Dev profile." / "What is MO2 warning me about?"

The assistant reads and changes MO2 through MO2's own plugin interface, so everything it does is exactly what you would have clicked, and MO2 keeps its own files consistent.

**You stay in charge:** installing a mod always needs your **Yes** in an MO2 dialog, new mods arrive disabled, files are moved but never deleted, and nothing can be changed while a tool such as xEdit or DynDOLOD is still running.

No extra software is needed: the plugin runs on MO2's own Python, and the bridge to the AI app is a PowerShell script that comes with Windows.

> Status: v0.12.0, a personal learning project. Every tool has been tested on a live MO2 2.5.2 with Skyrim Special Edition 1.7.104. Feedback and pull requests welcome.

## How it works

```
AI client ⇄ (stdio) ⇄ bridge.ps1 ⇄ (HTTP, 127.0.0.1 + token) ⇄ mo2_mcp plugin inside MO2 ⇄ MO2 plugin API (mobase)
```

- The plugin starts a small HTTP server bound to `127.0.0.1` only. Every request must carry a random token that the plugin writes to `connection.json` in its own folder.
- MO2's plugin API is not thread-safe, so every call is handed to MO2's GUI thread and runs exactly as if you had clicked it.
- `bridge.ps1` is what your MCP client starts. It forwards each JSON-RPC message to the plugin. When MO2 is closed it answers by itself, so the client keeps the tools listed and simply gets "MO2 is not running" until you start it.

## Tools

| Tool | What it does |
|---|---|
| `get_status` | MO2/game versions, paths, profile, mod and plugin counts, files in Overwrite, running tools |
| `list_mods` | Left pane in priority order; filter by text, enabled, or one separator |
| `list_plugins` | Right pane with load order, flags (master/light/medium/no records) and providing mod |
| `get_mod` | Version, Nexus id, notes, plugins and (optionally) file list of one mod |
| `file_origins` | Which mod wins a file in the virtual Data folder, and which it overrides |
| `get_mod_conflicts` | Loose-file conflicts of one mod: which mods it overrides and which override it, with examples |
| `plugin_header` | Reads plugin files directly: flags, header version, masters, records and new records, and whether each could be a light (ESL) plugin as is, needs header 1.71, needs FormID compacting, or has too many records. Without names it checks every enabled full plugin and counts your full plugin slots. Reads only |
| `list_skse_plugins` | Every SKSE plugin DLL in your mods (enabled or not) and the game's Data folder: its mod, whether another copy wins, and whether it loaded in the last game start (read from `skse64.log`, with the plugin's name and version) |
| `check_outputs` | Whether generated output is out of date: for each Pandora, PGPatcher, xLODGen, TexGen and DynDOLOD output mod, when it was made, which enabled mods have relevant files newer than it, whether the profile's lists were saved since, masters its plugins need that are no longer enabled, and for Pandora which patches were ticked in the last run. Reads only |
| `check_community_shaders` | Community Shaders: which mod provides `CommunityShaders.dll` (and other copies), every feature `.ini` with its version and winning mod, separate feature mods that override the version the core ships, each feature's status at the last game start and the warnings in `CommunityShaders.log`, and the shader cache. Reads only |
| `read_log` | Last lines of a log: MO2's own or usvfs, or a tool run through MO2 — DynDOLOD, TexGen, xLODGen and xEdit (last session only, found from the configured executables; for xEdit also what Quick Auto Clean removed, for DynDOLOD its summary topics and any `bugreport.txt`), Pandora's `Engine.log`, LOOT, or any SKSE plugin's log. Filters: text, warnings and errors only |
| `list_executables` | Executables configured in MO2 |
| `set_mods_enabled` / `set_mod_priority` | Enable/disable and move mods (`priority` or `after` another mod/separator) |
| `set_plugins_enabled` / `set_plugin_priority` | Enable/disable and move plugins |
| `refresh` | Refresh MO2 (F5) and wait until it has finished |
| `create_separator` / `rename_mod` | Add a separator (optionally placed), rename mods and separators |
| `list_notifications` | MO2's notifications (the warning-triangle list) with details and whether MO2 offers a guided fix. Briefly opens and closes MO2's notifications window |
| `list_profiles` / `switch_profile` | List profiles; switch the active one exactly as MO2's profile box does (refused while MO2 is locked by a running program) |
| `create_mod_from_overwrite` | Move Overwrite (or some of its folders) into a new or existing mod; `dry_run` shows the plan first. Files are moved, never deleted |
| `loot_sort` | Sort with your standalone LOOT (the LOOT executable configured in MO2, not MO2's built-in sort): runs it with LOOT's `--auto-sort` option, waits, refreshes and lists only the plugins that moved, plus LOOT's messages for your enabled plugins. `dry_run` shows LOOT's last messages and what its last sort moved without sorting |
| `run_executable` / `wait_for_run` / `list_runs` | Start a configured executable through the VFS, wait for it, refresh afterwards |
| `install_mod` | Install an archive — **only after the user confirms a Yes/No dialog in MO2** |
| `download_mod` / `wait_for_download` | Download a Nexus file into MO2's downloads folder through MO2's own Nexus login (needs Nexus Premium), and wait for it |

Read-only tools are marked `readOnlyHint` so clients can auto-approve them.

## Install

Requirements: Windows, Mod Organizer 2 **2.5.x** (with its Python plugin support), an MCP client that can start a local (stdio) server.

1. Download this repository and copy the `mo2_mcp` folder to `<MO2 install>\plugins\mo2_mcp`.
2. Start MO2. The plugin appears as **Claude MCP Server** under *Settings → Plugins* and writes `connection.json` and `tools.json` next to itself.
3. Add the bridge to your MCP client. For the Claude desktop app, open its config (*Settings → Developer → Edit Config*; in some versions *Settings → Desktop app → Extensions*) and add inside `"mcpServers"`:

   ```json
   "mo2": {
     "command": "powershell.exe",
     "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
              "C:\\path\\to\\Mod Organizer\\plugins\\mo2_mcp\\bridge.ps1"]
   }
   ```

   Note: the Microsoft Store/MSIX build of the Claude app may keep its config under `%LOCALAPPDATA%\Claude-Data\…\claude_desktop_config.json` instead of `%APPDATA%\Claude\`. Use the app's own "Edit config" button to find it.
4. Fully quit and restart the client.

### Settings (MO2 → Settings → Plugins → Claude MCP Server)

| Setting | Default | |
|---|---|---|
| `port` | `52525` | Local port. Change it if something else uses it. |
| `extra_instructions` | *(empty)* | Text appended to the instructions the AI receives, e.g. "Follow the Step SkyrimSE 3.0 guide; personal mods go under My Additions." |

## Safety

- Listens on `127.0.0.1` only; requests need the token from `connection.json`, a local `Host` header and no browser `Origin` header.
- `install_mod` always shows a Yes/No dialog in MO2. Changes are refused while a program started with `run_executable` is still running.
- `download_mod` uses MO2's own Nexus login (`IDownloadManager.startDownloadNexusFile`). The plugin never reads, stores or returns your Nexus API key. It shows no dialog in MO2, so the AI is told to download only files you approved in chat; the download only lands in MO2's downloads folder, and installing it still goes through `install_mod`'s dialog.
- `connection.json` and `tools.json` are machine-specific and must never be committed (see `.gitignore`).
- Anything that can read your user profile can read the token — the same trust boundary as MO2 itself. See [SECURITY.md](SECURITY.md).

## Development

```bash
pip install PyQt6 mobase-stubs pyright
pyright                                   # type check against the official mobase stubs
QT_QPA_PLATFORM=offscreen python tests/test_e2e.py   # end-to-end test against a fake MO2
```

The test starts the real plugin and HTTP server against a fake organizer (`tests/mobase.py` is a tiny runtime stand-in for `mobase`) and exercises every tool over HTTP.

Every tool has also run against a live MO2 2.5.2 with Skyrim SE 1.7.104; the results are in [issue #6](https://github.com/Wasarion/mo2-mcp/issues/6). Not tried live: installing an archive with a FOMOD installer (MO2 shows its own installer dialog to the user).

## Limits

- Only tested with Skyrim Special Edition and MO2 2.5.2. Other games MO2 manages may work but are untested.
- `switch_profile` and `list_notifications` work through MO2's own window (MO2's plugin interface has no way to do them), so they depend on MO2's window layout and may need updating for a future MO2 version.

## Credits

`create_separator`, `rename_mod`, `get_mod_conflicts`, `read_log` and waiting for MO2's refresh follow the approach of [MCP - MO2](https://www.nexusmods.com/site/mods/2549) by Antiarc123 (GPL-3.0-or-later), a larger MO2 MCP plugin worth a look.

## License

[GPL-3.0-or-later](LICENSE). Mod Organizer 2 is GPL-3 as well.

Written with AI assistance (Claude), reviewed and tested by the author.
