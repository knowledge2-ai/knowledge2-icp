"""Anonymous Parallel Search MCP over Streamable HTTP, using only the stdlib."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .tenant import Branding


MCP_URL = "https://search.parallel.ai/mcp"
PROTOCOL_VERSION = "2025-06-18"
MAX_RESPONSE_BYTES = 5_000_000
# One discovery conversation per process, reused across searches and MCP sessions.
_DISCOVERY_SESSION_ID = uuid.uuid4().hex


class ParallelSearchError(RuntimeError):
    pass


def search_web(query: str, *, timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
    """Return source URLs, titles and excerpts without loading any API credentials.

    The timeout budget covers initialization, discovery and search together.
    Interrupts propagate to the synchronous caller; errors never select another
    search provider.
    """
    transport = _MCPTransport(timeout_seconds)
    initialized = transport.call("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "knowledge2-icp", "version": "0.1.0"},
    })
    if initialized.get("protocolVersion") != PROTOCOL_VERSION:
        raise ParallelSearchError("Parallel MCP returned an unsupported protocol version.")
    transport.initialized = True
    transport.call("notifications/initialized", {}, notification=True)
    tools = transport.call("tools/list", {}).get("tools", [])
    if not isinstance(tools, list) or not any(
        isinstance(tool, dict) and tool.get("name") == "web_search" for tool in tools
    ):
        raise ParallelSearchError("Parallel MCP does not offer web_search.")
    result = transport.call("tools/call", {
        "name": "web_search",
        "arguments": {
            "objective": f"Find company websites matching this discovery brief: {query}",
            "search_queries": [query],
            "session_id": _DISCOVERY_SESSION_ID,
        },
    })
    content = result.get("content", [])
    if not isinstance(content, list):
        raise ParallelSearchError("Parallel search returned invalid content.")
    if result.get("isError"):
        messages = [item["text"] for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
        raise ParallelSearchError("Parallel search failed: " + " ".join(messages)[:500])
    data = result.get("structuredContent")
    if not isinstance(data, dict):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    data = json.loads(item.get("text", ""))
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict) and "results" in data:
                    break
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ParallelSearchError("Parallel search returned an invalid results payload.")
    return [item for item in data["results"] if isinstance(item, dict)]


class _MCPTransport:
    def __init__(self, timeout_seconds: float) -> None:
        self.deadline = time.monotonic() + timeout_seconds
        self.session_id = ""
        self.initialized = False
        self.next_id = 0

    def call(self, method: str, params: dict[str, Any], *, notification: bool = False) -> dict[str, Any]:
        self.next_id += 1
        request_id = self.next_id
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = request_id
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": Branding().discovery_user_agent,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.initialized:
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ParallelSearchError("Parallel search timed out.")
        request = Request(MCP_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=remaining) as response:
                if method == "initialize":
                    self.session_id = response.headers.get("Mcp-Session-Id", "")
                if notification:
                    return {}
                message = _read_message(response, request_id)
        except HTTPError as exc:
            raise ParallelSearchError(f"Parallel MCP returned HTTP {exc.code}.") from exc
        except (URLError, OSError) as exc:
            raise ParallelSearchError("Parallel MCP connection failed or timed out.") from exc
        except (ValueError, UnicodeError) as exc:
            raise ParallelSearchError("Parallel MCP returned an invalid response.") from exc
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or message.get("id") != request_id:
            raise ParallelSearchError("Parallel MCP returned an unexpected response ID.")
        if "error" in message:
            raise ParallelSearchError("Parallel MCP rejected the request.")
        if not isinstance(message.get("result"), dict):
            raise ParallelSearchError("Parallel MCP returned an invalid result.")
        return message["result"]


def _read_message(response: Any, request_id: int) -> Any:
    if "text/event-stream" not in response.headers.get("Content-Type", ""):
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ParallelSearchError("Parallel MCP response is too large.")
        return json.loads(raw)
    # Stop at the matching event, without waiting for a persistent SSE stream to
    # close. Ignore server notifications and comments while awaiting the reply.
    size = 0
    data: list[str] = []
    while True:
        raw = response.readline(MAX_RESPONSE_BYTES - size + 1)
        size += len(raw)
        if size > MAX_RESPONSE_BYTES:
            raise ParallelSearchError("Parallel MCP response is too large.")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line and data:
            message = json.loads("\n".join(data))
            data = []
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        if not raw:
            raise ParallelSearchError("Parallel MCP stream ended without a result.")
