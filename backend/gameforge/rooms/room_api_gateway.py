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
import math
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

_ALLOWED_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
_MAX_EXTERNAL_URL_CHARS = 4096
_MAX_EXTERNAL_TIMEOUT_SECONDS = 30.0
_FORBIDDEN_FORWARD_HEADERS = frozenset({
    "host",
    "proxy-authorization",
    "proxy-connection",
    "connection",
    "transfer-encoding",
})


def _canonical_allowed_host(hostname: str) -> str:
    """Return the operator-owned allowlist value, never the request-owned value."""
    for allowed in _EXTERNAL_API_HOSTS:
        if hostname == allowed:
            return allowed
    raise ValueError("external API URL is not on the HTTPS host allowlist")


def _resolve_public_host(hostname: str) -> None:
    """Fail closed unless every current address for the allowlisted host is public."""
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("external API host could not be resolved") from exc
    if not addresses:
        raise ValueError("external API host resolved to no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("external API host resolves to a non-public address")


def _origin_for_host(hostname: str) -> str:
    """Build a fixed HTTPS origin from a canonical allowlist entry."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        return f"https://{hostname}"
    if literal.version == 6:
        return f"https://[{literal.compressed}]"
    return f"https://{literal.compressed}"


def _prepare_external_request(url: str) -> tuple[str, str]:
    """Split untrusted input into a trusted origin and a relative request target.

    Keeping caller-controlled path/query data out of the authority passed to the
    HTTP client removes the full-URL SSRF sink while retaining the explicit
    operator allowlist and public-address checks.
    """
    if not isinstance(url, str) or not url or len(url) > _MAX_EXTERNAL_URL_CHARS:
        raise ValueError("external API URL is missing or exceeds the size limit")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ValueError("external API URL contains control characters")

    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
        or "\\" in parsed.path
    ):
        raise ValueError("external API URL must be a plain HTTPS authority")

    canonical_host = _canonical_allowed_host(hostname)
    _resolve_public_host(canonical_host)

    # Never forward a network-path reference (//host/path). Prefix a single
    # slash after stripping all caller-supplied leading slashes.
    safe_path = "/" + (parsed.path or "").lstrip("/")
    request_target = safe_path
    if parsed.query:
        request_target += "?" + parsed.query
    return _origin_for_host(canonical_host), request_target


def _validate_external_url(url: str) -> None:
    """Compatibility validator backed by the structural SSRF boundary."""
    _prepare_external_request(url)


def _safe_method(value: Any) -> str:
    method = str(value or "GET").upper()
    if method not in _ALLOWED_HTTP_METHODS:
        raise ValueError("external API method is not allowed")
    return method


def _safe_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("external API timeout is invalid") from exc
    if not math.isfinite(timeout) or timeout <= 0 or timeout > _MAX_EXTERNAL_TIMEOUT_SECONDS:
        raise ValueError("external API timeout is outside the allowed range")
    return timeout


def _safe_headers(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("external API headers must be a mapping")
    headers: dict[str, str] = {}
    for raw_name, raw_value in value.items():
        name = str(raw_name).strip()
        header_value = str(raw_value)
        if not name or name.lower() in _FORBIDDEN_FORWARD_HEADERS:
            raise ValueError("external API contains a forbidden forwarding header")
        if any(ord(ch) < 32 and ch != "\t" for ch in name + header_value) or "\r" in header_value or "\n" in header_value:
            raise ValueError("external API header contains control characters")
        headers[name] = header_value
    return headers


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
    except Exception:  # noqa: BLE001
        return {"channel": "mcp", "query": query, "ok": False, "error": "mcp_query_failed"}


async def _api_query(target: dict) -> dict:
    """Call one explicitly allowlisted external API."""
    url = target.get("url", "")
    name = target.get("name", url)
    if not _EXTERNAL_ENABLED:
        return {"channel": "api", "target": name, "ok": True, "disabled": True,
                "note": "external APIs disabled (inward-focused); set GAMEFORGE_ENABLE_EXTERNAL_APIS=1"}
    try:
        base_url, request_target = _prepare_external_request(url)
        method = _safe_method(target.get("method", "GET"))
        timeout = _safe_timeout(target.get("timeout", 8))
        headers = _safe_headers(target.get("headers"))
        import httpx
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=False,
        ) as c:
            r = await c.request(
                method,
                request_target,
                params=target.get("params"),
                headers=headers,
                json=target.get("json"),
            )
            body = r.text[:2000]
            return {"channel": "api", "target": name, "ok": r.is_success,
                    "status": r.status_code, "body": body}
    except Exception:  # noqa: BLE001
        return {"channel": "api", "target": name, "ok": False, "error": "api_query_failed"}


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
