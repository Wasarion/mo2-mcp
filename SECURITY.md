# Security

## What this plugin can do

While MO2 is running with the plugin enabled, anything that can talk to it can enable, disable and reorder mods and plugins, refresh MO2, start executables through MO2's virtual filesystem (including any absolute path), and ask to install an archive (installs always need a Yes in an MO2 dialog).

## How it is protected

- The HTTP server binds to `127.0.0.1` only and is never reachable from the network.
- Every request needs a 256-bit random token stored in `connection.json` next to the plugin (compared in constant time).
- Requests must use a `127.0.0.1`/`localhost` `Host` header (blocks DNS rebinding) and must not carry a browser `Origin` header (blocks web pages).
- Request bodies are limited to 1 MiB.
- Mod installs require explicit confirmation in MO2.

The trust boundary is your Windows user account: a program running as you can read `connection.json`, just as it could edit MO2's files directly.

## Never commit

`mo2_mcp/connection.json` (your token) and `mo2_mcp/tools.json`. Both are in `.gitignore`. If you ever leaked a token, delete `connection.json` and restart MO2 to get a new one.

## Reporting a vulnerability

Please use GitHub's private reporting (**Security → Report a vulnerability**) instead of a public issue. You will get an answer as soon as possible.
