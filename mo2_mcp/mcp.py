"""Minimal MCP (Model Context Protocol) server core: JSON-RPC 2.0, tools only.

No MO2 dependency, so it can be tested outside Mod Organizer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("mo2_mcp")

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
    """An expected failure, reported to the model as a tool result with isError=true."""


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    required: list[str] = field(default_factory=list)
    writes: bool = False          # changes MO2 state
    main_thread: bool = True      # must run on MO2's GUI thread
    timeout: float = 60.0         # seconds to wait for the GUI thread
    destructive: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": not self.writes,
                "destructiveHint": self.destructive,
                "openWorldHint": False,
            },
        }


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _check_args(tool: Tool, args: dict[str, Any]) -> None:
    for key in tool.required:
        if key not in args:
            raise RpcError(INVALID_PARAMS, f"{tool.name}: missing required argument '{key}'")
    for key, value in args.items():
        spec = tool.properties.get(key)
        if spec is None:
            raise RpcError(INVALID_PARAMS, f"{tool.name}: unknown argument '{key}'")
        expected = _JSON_TYPES.get(spec.get("type", ""))
        if expected is None:
            continue
        ok = isinstance(value, expected)
        if spec["type"] in ("integer", "number") and isinstance(value, bool):
            ok = False
        if not ok:
            raise RpcError(INVALID_PARAMS, f"{tool.name}: argument '{key}' must be {spec['type']}")


class McpServer:
    """Turns JSON-RPC messages into tool calls.

    `executor(tool, args)` decides how a tool runs (thread, guards); the default
    just calls the handler.
    """

    def __init__(
        self,
        name: str,
        version: str,
        tools: list[Tool],
        instructions: str = "",
        executor: Callable[[Tool, dict[str, Any]], Any] | None = None,
    ):
        self.name = name
        self.version = version
        self.instructions = instructions
        self.tools = {t.name: t for t in tools}
        self.executor = executor or (lambda tool, args: tool.handler(args))

    def tool_list(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    # -- transport entry point ------------------------------------------------
    def handle_payload(self, data: bytes) -> bytes | None:
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            return _dump(_error(None, PARSE_ERROR, f"Parse error: {e}"))
        if isinstance(message, list):
            replies = [r for r in (self.handle(m) for m in message) if r is not None]
            return _dump(replies) if replies else None
        reply = self.handle(message)
        return _dump(reply) if reply is not None else None

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, INVALID_REQUEST, "Invalid request")
        if "method" not in message:
            return None  # a response to something we never send; ignore
        is_notification = "id" not in message
        msg_id = message.get("id")
        params = message.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RpcError(INVALID_PARAMS, "params must be an object")
            result = self._dispatch(str(message["method"]), params)
        except RpcError as e:
            return None if is_notification else _error(msg_id, e.code, str(e))
        except Exception as e:  # noqa: BLE001 - never let the server die
            log.exception("MCP request failed")
            return None if is_notification else _error(msg_id, INTERNAL_ERROR, f"{type(e).__name__}: {e}")
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # -- methods --------------------------------------------------------------
    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            result: dict[str, Any] = {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version},
            }
            if self.instructions:
                result["instructions"] = self.instructions
            return result
        if method.startswith("notifications/"):
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tool_list()}
        if method == "tools/call":
            return self._call_tool(params)
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        tool = self.tools.get(name) if isinstance(name, str) else None
        if tool is None:
            raise RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise RpcError(INVALID_PARAMS, "arguments must be an object")
        _check_args(tool, args)
        try:
            value = self.executor(tool, args)
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:  # noqa: BLE001
            log.exception(f"tool {tool.name} failed")
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1)
        return {"content": [{"type": "text", "text": text}], "isError": False}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _dump(obj: Any) -> bytes:
    # One line, no raw newlines: the stdio bridge frames messages by line.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
