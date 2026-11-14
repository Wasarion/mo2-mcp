"""mo2-mcp: an MCP server plugin for Mod Organizer 2 (2.5.x).

Copyright (C) 2026 Wasarion
This program is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version. See LICENSE.

Install: copy this folder to <MO2>/plugins/mo2_mcp and restart MO2.
"""

import mobase

from .plugin import McpPlugin


def createPlugin() -> mobase.IPlugin:
    return McpPlugin()
