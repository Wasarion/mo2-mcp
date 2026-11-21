"""MO2 plugin: serves MO2's tools to Claude over MCP on 127.0.0.1 only."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import mobase
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from .invoker import MainThreadInvoker
from .mcp import McpServer, Tool, ToolError
from .procs import RunTracker
from .tools import Mo2Tools

# MO2's log handler prints the raw message without %-formatting, so log with f-strings.
log = logging.getLogger("mo2_mcp")

VERSION = "0.6.0"
HERE = Path(__file__).resolve().parent
CONNECTION_FILE = HERE / "connection.json"   # port + token, read by bridge.ps1
TOOLS_CACHE = HERE / "tools.json"            # tool list for the bridge while MO2 is closed
MAX_BODY = 1 << 20

INSTRUCTIONS = """Controls the user's running Mod Organizer 2 instance.
- Read before you change: get_status, list_mods, list_plugins.
- Mod priority 0 is the top of the left pane; higher priority wins file conflicts.
- Never install a mod unless the user approved that exact archive in chat. MO2 also asks them to confirm.
- Never download a Nexus file (download_mod) unless the user approved that exact file in chat.
- Changes are refused while a program started with run_executable is still running.
- After xEdit, DynDOLOD, Nemesis/Pandora etc. write output, refresh (wait_for_run does it for you)."""


class McpPlugin(mobase.IPlugin):
    def __init__(self) -> None:
        super().__init__()
        self._organizer: mobase.IOrganizer | None = None
        self._main_window: QMainWindow | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._invoker: MainThreadInvoker | None = None
        self._runs = RunTracker()

    # -- IPlugin -----------------------------------------------------------------
    def name(self) -> str:
        return "Claude MCP Server"

    def author(self) -> str:
        return "Wasarion"

    def description(self) -> str:
        return "Lets an MCP client (e.g. the Claude desktop app) control MO2 through a local bridge (127.0.0.1 only)."

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(VERSION)

    def settings(self) -> list[mobase.PluginSetting]:
        return [
            mobase.PluginSetting("port", "Local TCP port (127.0.0.1) for the MCP bridge", 52525),
            mobase.PluginSetting("extra_instructions", "Extra text appended to the instructions the AI client receives (e.g. your build's rules)", ""),
        ]

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        self._invoker = MainThreadInvoker()
        organizer.onUserInterfaceInitialized(self._on_ui)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop)
        try:
            self.start()
        except OSError as e:
            log.error(f"Claude MCP: could not start server: {e}")
        return True

    # -- server ------------------------------------------------------------------
    def _on_ui(self, window: QMainWindow) -> None:
        self._main_window = window

    def _confirm_install(self, archive: str, name: str) -> bool:
        text = f"Claude wants to install:\n\n{os.path.basename(archive)}"
        if name:
            text += f"\n\nas \"{name}\""
        answer = QMessageBox.question(
            self._main_window, "Claude – install mod?", text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _execute(self, tool: Tool, args: dict[str, Any]) -> Any:
        if tool.writes:
            busy = self._runs.active()
            if busy:
                raise ToolError(f"{busy[0].title} (run {busy[0].id}) is still running. Wait for it with wait_for_run first.")
        if not tool.main_thread:
            return tool.handler(args)
        assert self._invoker is not None
        return self._invoker.invoke(lambda: tool.handler(args), tool.timeout)

    def build_server(self) -> McpServer:
        assert self._organizer is not None and self._invoker is not None
        tools = Mo2Tools(self._organizer, self._runs, self._confirm_install, self._invoker.invoke, lambda: self._main_window)
        extra = self._organizer.pluginSetting(self.name(), "extra_instructions")
        instructions = INSTRUCTIONS + (f"\n{extra.strip()}" if isinstance(extra, str) and extra.strip() else "")
        return McpServer("mo2", VERSION, tools.tools(), instructions, self._execute)

    def start(self) -> None:
        assert self._organizer is not None
        setting = self._organizer.pluginSetting(self.name(), "port")
        port = int(setting) if isinstance(setting, (int, str)) and str(setting).isdigit() else 52525
        server = self.build_server()
        token = _load_or_create_token()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(server, token, port))
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, name="mo2-mcp", daemon=True).start()
        _write_json(CONNECTION_FILE, {"port": port, "token": token, "version": VERSION})
        _write_json(TOOLS_CACHE, server.tool_list())
        log.info(f"Claude MCP server listening on 127.0.0.1:{port}")

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def _make_handler(server: McpServer, token: str, port: int) -> type[BaseHTTPRequestHandler]:
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            log.debug("http: " + (format % args))

        def _send(self, code: int, body: bytes = b"") -> None:
            self.send_response(code)
            if body:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._send(405)

        def do_POST(self) -> None:  # noqa: N802
            # Host check blocks DNS rebinding, Origin check blocks browsers, the token blocks
            # every other local program that has not read connection.json.
            if self.path != "/mcp" or self.headers.get("Host", "") not in allowed_hosts:
                return self._send(404)
            if self.headers.get("Origin"):
                return self._send(403)
            if not hmac.compare_digest(self.headers.get("X-MO2-Token", ""), token):
                return self._send(401)
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._send(413)
            reply = server.handle_payload(self.rfile.read(length))
            if reply is None:
                return self._send(202)
            self._send(200, reply)

    return Handler


def _load_or_create_token() -> str:
    try:
        token = json.loads(CONNECTION_FILE.read_text(encoding="utf-8"))["token"]
        if isinstance(token, str) and len(token) >= 32:
            return token
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return secrets.token_urlsafe(32)


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
