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
import json
import math
import os
import re
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
_MAX_RESPONSE_BYTES = 256 * 1024
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_MCP_QUERIES = 32
_MAX_API_TARGETS = 32
_MAX_SOURCES = 16
_MAX_CONCURRENT_QUERIES = 8
_MAX_JSON_DEPTH = 8
_MAX_JSON_NODES = 1024
_FORBIDDEN_FORWARD_HEADERS = frozenset({
    "host",
    "proxy-authorization",
    "proxy-connection",
    "connection",
    "transfer-encoding",
    "content-length",
    "te",
    "trailer",
    "upgrade",
    "keep-alive",
})


def _canonical_allowed_host(hostname: str) -> str:
    """Return the operator-owned allowlist value, never the request-owned value."""
    for allowed in _EXTERNAL_API_HOSTS:
        if hostname == allowed:
            return allowed
    raise ValueError("external API URL is not on the HTTPS host allowlist")


def _resolve_public_host(hostname: str) -> str:
    """Resolve once, reject mixed/private DNS answers, and select a pinned IP.

    Passing the approved IP as the actual HTTP connection authority prevents a
    later DNS rebind from changing the network destination after validation.
    """
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("external API host could not be resolved") from exc
    if not addresses:
        raise ValueError("external API host resolved to no addresses")
    approved: set[str] = set()
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except (ValueError, IndexError, TypeError) as exc:
            raise ValueError("external API host returned an invalid address") from exc
        if not ip.is_global:
            raise ValueError("external API host resolves to a non-public address")
        approved.add(ip.compressed)
    return sorted(approved, key=lambda item: (ipaddress.ip_address(item).version, item))[0]


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
    if type(value) is not dict or len(value) > 32:
        raise ValueError("external API headers exceed the allowlisted shape")
    headers: dict[str, str] = {}
    total = 0
    for raw_name, raw_value in value.items():
        if type(raw_name) is not str or type(raw_value) is not str:
            raise ValueError("external API header keys and values must be strings")
        name, header_value = raw_name, raw_value
        if (not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}", name)
                or name.lower() in _FORBIDDEN_FORWARD_HEADERS):
            raise ValueError("external API contains a forbidden forwarding header")
        if (len(header_value) > 8192
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in header_value)):
            raise ValueError("external API header contains control characters")
        total += len(name) + len(header_value)
        if total > 16 * 1024:
            raise ValueError("external API header budget exceeded")
        headers[name] = header_value
    return headers


def _bounded_json(value: Any) -> Any:
    """Validate request JSON before it can allocate large HTTPX buffers."""
    if value is None:
        return None
    remaining = _MAX_JSON_NODES

    def check(node: Any, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > _MAX_JSON_DEPTH:
            raise ValueError("external API JSON structure exceeds budget")
        if type(node) in (str, int, bool) or node is None:
            if type(node) is str and len(node) > _MAX_REQUEST_BYTES:
                raise ValueError("external API JSON text exceeds budget")
            return
        if type(node) is float:
            if not math.isfinite(node):
                raise ValueError("external API JSON has nonfinite number")
            return
        if type(node) is list:
            if len(node) > _MAX_JSON_NODES:
                raise ValueError("external API JSON array exceeds budget")
            for item in node:
                check(item, depth + 1)
            return
        if type(node) is dict:
            if len(node) > _MAX_JSON_NODES:
                raise ValueError("external API JSON mapping exceeds budget")
            for key, item in node.items():
                if type(key) is not str or len(key) > 256:
                    raise ValueError("external API JSON keys must be bounded strings")
                check(item, depth + 1)
            return
        raise ValueError("external API JSON contains unsupported types")

    check(value, 0)
    if len(json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")) > _MAX_REQUEST_BYTES:
        raise ValueError("external API request exceeds byte budget")
    return value


def _safe_params(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if type(value) is not dict or len(value) > 16:
        raise ValueError("external API query parameters exceed budget")
    result = {}
    for key, item in value.items():
        if type(key) is not str or not 1 <= len(key) <= 64:
            raise ValueError("external API query parameter name invalid")
        if type(item) not in (str, int, float, bool):
            raise ValueError("external API query parameter type invalid")
        if type(item) is float and not math.isfinite(item):
            raise ValueError("external API query parameter is nonfinite")
        text = str(item)
        if len(text) > 512:
            raise ValueError("external API query parameter exceeds budget")
        result[key] = text
    return result


async def _bounded_http_body(response: Any) -> str:
    """Bound streamed *decompressed* response bytes, never buffer an entire body."""
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid external API content length") from exc
        if size < 0 or size > _MAX_RESPONSE_BYTES:
            raise ValueError("external API response exceeds byte budget")
    chunks: list[bytes] = []
    size = 0
    async for data in response.aiter_bytes():
        size += len(data)
        if size > _MAX_RESPONSE_BYTES:
            raise ValueError("external API response exceeds byte budget")
        chunks.append(data)
    return b"".join(chunks).decode("utf-8", errors="replace")[:2000]

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
    """Call one explicitly allowlisted HTTPS endpoint under strict limits."""
    if type(target) is not dict:
        return {"channel": "api", "target": "external_api", "ok": False,
                "error": "api_query_failed"}
    # Never echo an entire caller-controlled URL containing bearer tokens.
    raw_name = target.get("name", "external_api")
    name = raw_name if type(raw_name) is str and 1 <= len(raw_name) <= 80 else "external_api"
    if not _EXTERNAL_ENABLED:
        return {"channel": "api", "target": name, "ok": True, "disabled": True,
                "note": "external APIs disabled (inward-focused); set GAMEFORGE_ENABLE_EXTERNAL_APIS=1"}
    try:
        url = target.get("url", "")
        # DNS is blocking; neither resolution can hold the event loop hostage.
        base_url, request_target = await asyncio.wait_for(
            asyncio.to_thread(_prepare_external_request, url), timeout=5.0
        )
        method = _safe_method(target.get("method", "GET"))
        timeout = _safe_timeout(target.get("timeout", 8))
        headers = _safe_headers(target.get("headers")) or {}
        parameters = _safe_params(target.get("params"))
        body_json = _bounded_json(target.get("json"))
        hostname = urlsplit(base_url).hostname
        if hostname is None:
            raise ValueError("external API host is missing")
        # Recheck DNS and connect to exactly that vetted public IP. No HTTPX
        # DNS re-resolution, redirect, environment proxy or credentials.
        pinned_ip = await asyncio.wait_for(
            asyncio.to_thread(_resolve_public_host, hostname), timeout=5.0
        )
        headers["Host"] = hostname
        import httpx

        async with httpx.AsyncClient(
            base_url=_origin_for_host(pinned_ip),
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                method,
                request_target,
                params=parameters,
                headers=headers,
                json=body_json,
                extensions={"sni_hostname": hostname},
            ) as response:
                body = await _bounded_http_body(response)
                return {"channel": "api", "target": name, "ok": response.is_success,
                        "status": response.status_code, "body": body}
    except Exception:  # noqa: BLE001
        return {"channel": "api", "target": name, "ok": False, "error": "api_query_failed"}

async def query_concurrent(room_id: str, mcp_queries: list[str] | None = None,
                           api_targets: list[dict] | None = None,
                           sources: list[str] | None = None) -> dict:
    """Fan every MCP query + external API target out CONCURRENTLY for a room.
    Returns per-channel results plus timing so callers can see the parallelism."""
    mcp_queries = mcp_queries if mcp_queries is not None else []
    api_targets = api_targets if api_targets is not None else []
    if (type(room_id) is not str or not 1 <= len(room_id) <= 128
            or type(mcp_queries) is not list or len(mcp_queries) > _MAX_MCP_QUERIES
            or type(api_targets) is not list or len(api_targets) > _MAX_API_TARGETS
            or any(type(q) is not str or not 1 <= len(q) <= 4096 for q in mcp_queries)
            or any(type(target) is not dict for target in api_targets)
            or (sources is not None and (
                type(sources) is not list or len(sources) > _MAX_SOURCES
                or any(type(s) is not str or not 1 <= len(s) <= 128 for s in sources)
            ))):
        raise ValueError("room fanout request exceeds admission budget")
    t0 = time.perf_counter()

    # No unbounded connection/thread fanout for a room.
    slots = asyncio.Semaphore(_MAX_CONCURRENT_QUERIES)

    async def bounded(operation):
        async with slots:
            return await operation

    tasks = [bounded(_mcp_query(q, sources)) for q in mcp_queries]
    tasks += [bounded(_api_query(t)) for t in api_targets]
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
