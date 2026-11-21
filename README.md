# mo2-mcp

An [MCP](https://modelcontextprotocol.io) server that runs **inside Mod Organizer 2** and lets an AI client (for example the Claude desktop app) work with your live MO2: read the mod and plugin lists, enable and move mods, run your configured tools (xEdit, LOOT, DynDOLOD, …) and install archives you approved.

No screenshots, no clicking, no extra runtimes: the plugin uses MO2's own Python and the Python standard library, and the bridge is a PowerShell script that ships with Windows.

> Status: early (v0.3.0). Tested on MO2 2.5.2 with Skyrim Special Edition. Feedback and pull requests welcome.

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
| `read_log` | Last lines of MO2's log or the newest usvfs log, optionally filtered |
| `list_executables` | Executables configured in MO2 |
| `set_mods_enabled` / `set_mod_priority` | Enable/disable and move mods (`priority` or `after` another mod/separator) |
| `set_plugins_enabled` / `set_plugin_priority` | Enable/disable and move plugins |
| `refresh` | Refresh MO2 (F5) and wait until it has finished |
| `create_separator` / `rename_mod` | Add a separator (optionally placed), rename mods and separators |
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

Not yet verified against a live MO2: `download_mod`, `wait_for_download`, `install_mod`, `set_plugin_priority`, `set_plugins_enabled`, `run_executable`, `create_separator`, `rename_mod`. Reports welcome.

## Roadmap / help wanted

- Move Overwrite into a new mod (DynDOLOD, xLODGen, TexGen output)
- Switch profiles
- Read MO2's problems/diagnostics list
- Test on other games and MO2 versions

## Credits

`create_separator`, `rename_mod`, `get_mod_conflicts`, `read_log` and waiting for MO2's refresh follow the approach of [MCP - MO2](https://www.nexusmods.com/site/mods/2549) by Antiarc123 (GPL-3.0-or-later), a larger MO2 MCP plugin worth a look.

## License

[GPL-3.0-or-later](LICENSE). Mod Organizer 2 is GPL-3 as well.

Written with AI assistance (Claude), reviewed and tested by the author.
