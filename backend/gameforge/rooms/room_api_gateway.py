"""
gameforge/rooms/room_api_gateway.py — Rooms query external APIs + MCP CONCURRENTLY.

Every one of the 1000 CNS rooms can now fan out a batch of queries across:
  * the MCP connector mesh (internal knowledge sources), and
  * external HTTP APIs

…all at once via ``asyncio.gather``. The sync MCP calls are off-loaded to threads
so nothing blocks the event loop.

Inward-focused by default: real outbound HTTP is only performed when the env flag
``GAMEFORGE_ENABLE_EXTERNAL_APIS=1`` is set; otherwise external targets return a
safe "disabled" stub so the mesh still exercises concurrency without egress.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import time
from urllib.parse import urlsplit
from typing import Any

_EXTERNAL_ENABLED = os.getenv("GAMEFORGE_ENABLE_EXTERNAL_APIS", "0") == "1"
_EXTERNAL_API_HOSTS = frozenset(
    host.strip().lower()
    for host in os.getenv("GAMEFORGE_EXTERNAL_API_HOSTS", "").split(",")
    if host.strip()
)

_mcp = None


def _validate_external_url(url: str) -> None:
    """Allow only explicitly configured HTTPS hosts resolving to public IPs."""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname or hostname not in _EXTERNAL_API_HOSTS:
        raise ValueError("external API URL is not on the HTTPS host allowlist")
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("external API host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("external API host resolves to a non-public address")


def _get_mcp():
    global _mcp
    if _mcp is None:
        from gameforge.exocortex.agentic.mcp_connectors import MCPConnectors
        _mcp = MCPConnectors()
    return _mcp


async def _mcp_query(query: str, sources: list[str] | None) -> dict:
    """Off-load the synchronous MCP router to a thread."""
    try:
        mcp = _get_mcp()
        res = await asyncio.to_thread(mcp.route_query, query, sources)
        return {"channel": "mcp", "query": query, "ok": True, "result": res}
    except Exception as e:  # noqa: BLE001
        return {"channel": "mcp", "query": query, "ok": False, "error": f"{type(e).__name__}: {e}"[:160]}


async def _api_query(target: dict) -> dict:
    """Call one explicitly allowlisted external API."""
    url = target.get("url", "")
    name = target.get("name", url)
    if not _EXTERNAL_ENABLED:
        return {"channel": "api", "target": name, "ok": True, "disabled": True,
                "note": "external APIs disabled (inward-focused); set GAMEFORGE_ENABLE_EXTERNAL_APIS=1"}
    try:
        _validate_external_url(url)
        import httpx
        async with httpx.AsyncClient(timeout=target.get("timeout", 8), follow_redirects=False) as c:
            r = await c.request(target.get("method", "GET"), url,
                                params=target.get("params"), headers=target.get("headers"),
                                json=target.get("json"))
            body = r.text[:2000]
            return {"channel": "api", "target": name, "ok": r.is_success,
                    "status": r.status_code, "body": body}
    except Exception as e:  # noqa: BLE001
        return {"channel": "api", "target": name, "ok": False, "error": f"{type(e).__name__}: {e}"[:160]}


async def query_concurrent(room_id: str, mcp_queries: list[str] | None = None,
                           api_targets: list[dict] | None = None,
                           sources: list[str] | None = None) -> dict:
    """Fan every MCP query + external API target out CONCURRENTLY for a room.
    Returns per-channel results plus timing so callers can see the parallelism."""
    mcp_queries = mcp_queries or []
    api_targets = api_targets or []
    t0 = time.perf_counter()

    tasks = [_mcp_query(q, sources) for q in mcp_queries]
    tasks += [_api_query(t) for t in api_targets]
    results = await asyncio.gather(*tasks) if tasks else []

    mcp_res = [r for r in results if r["channel"] == "mcp"]
    api_res = [r for r in results if r["channel"] == "api"]
    return {
        "room_id": room_id,
        "concurrent": True,
        "external_apis_enabled": _EXTERNAL_ENABLED,
        "counts": {"mcp": len(mcp_res), "api": len(api_res)},
        "ok": all(r["ok"] for r in results) if results else True,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "mcp": mcp_res,
        "api": api_res,
    }
