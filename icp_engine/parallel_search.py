"""Opt-in anonymous Parallel Search MCP using the official Python MCP client."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from .tenant import Branding


MCP_URL = "https://search.parallel.ai/mcp"
# Reuse the discovery conversation identity across searches and MCP sessions.
_DISCOVERY_SESSION_ID = uuid.uuid4().hex


class ParallelSearchError(RuntimeError):
    pass


def search_web(query: str, *, timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
    """Search without credentials; bound the entire MCP operation by a deadline."""
    try:
        import anyio
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.types import Implementation
    except ImportError as exc:
        raise ParallelSearchError("Install the Parallel discovery extra: pip install -e '.[parallel]'.") from exc

    async def search() -> dict[str, Any]:
        with anyio.fail_after(timeout_seconds):
            async with httpx.AsyncClient(
                headers={"User-Agent": Branding().discovery_user_agent},
                timeout=timeout_seconds,
            ) as client:
                async with streamable_http_client(MCP_URL, http_client=client) as (read, write, _):
                    async with ClientSession(
                        read, write, client_info=Implementation(name="knowledge2-icp", version="0.1.0")
                    ) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        if not any(tool.name == "web_search" for tool in tools.tools):
                            raise ParallelSearchError("Parallel MCP does not offer web_search.")
                        result = await session.call_tool("web_search", {
                            "objective": f"Find company websites matching this discovery brief: {query}",
                            "search_queries": [query],
                            "session_id": _DISCOVERY_SESSION_ID,
                        })
                        return result.model_dump(by_alias=True)

    try:
        result = asyncio.run(search())
    except Exception as exc:
        # SDK task groups can wrap transport or tool errors in ExceptionGroups.
        # Cancellation/KeyboardInterrupt are BaseExceptions and propagate.
        raise ParallelSearchError(_error_message(exc)) from exc
    content = result.get("content", [])
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


def _error_message(error: BaseException) -> str:
    if isinstance(error, ParallelSearchError):
        return str(error)
    if isinstance(error, TimeoutError):
        return "Parallel search timed out."
    nested = getattr(error, "exceptions", ())
    if nested:
        return _error_message(nested[0])
    response = getattr(error, "response", None)
    if response is not None:
        return f"Parallel MCP returned HTTP {response.status_code}."
    return "Parallel MCP request failed or timed out."
