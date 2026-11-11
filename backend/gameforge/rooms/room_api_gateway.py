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
import socket
import time
from typing import Any
from urllib.parse import urlsplit

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
_MAX_EXTERNAL_RESPONSE_BYTES = 64 * 1024
_MAX_EXTERNAL_REQUEST_BYTES = 16 * 1024
_MAX_EXTERNAL_TARGETS_PER_CALL = 32
_MAX_MCP_QUERIES_PER_CALL = 32
_MAX_TOTAL_CONCURRENT_JOBS = 48
_MAX_INFLIGHT_PER_CALL = 8
_FORBIDDEN_FORWARD_HEADERS = frozenset({
    "host", "authorization", "cookie", "set-cookie",
    "proxy-authorization", "proxy-connection", "proxy-authenticate",
    "connection", "transfer-encoding", "te", "upgrade",
    "forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip",
    "x-api-key", "x-auth-token",
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
    if len(addresses) > 32:
        raise ValueError("external API host has too many DNS addresses")
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
    if value is None:
        value = "GET"
    if type(value) is not str or len(value) > 16:
        raise ValueError("external API method is invalid")
    method = value.upper()
    if method not in _ALLOWED_HTTP_METHODS:
        raise ValueError("external API method is not allowed")
    return method


def _safe_timeout(value: Any) -> float:
    if type(value) not in (str, int, float) or (
        type(value) is str and len(value) > 16
    ):
        raise ValueError("external API timeout is invalid")
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
    if not isinstance(value, dict) or len(value) > 24:
        raise ValueError("external API headers must be a bounded mapping")
    headers: dict[str, str] = {}
    for raw_name, raw_value in value.items():
        if type(raw_name) is not str or type(raw_value) is not str:
            raise ValueError("external API header names and values must be strings")
        name = raw_name.strip()
        if not 1 <= len(name) <= 64 or not all(
            ch.isascii() and (ch.isalnum() or ch == "-") for ch in name
        ):
            raise ValueError("external API header name is invalid")
        if name.lower() in _FORBIDDEN_FORWARD_HEADERS:
            raise ValueError("external API contains a forbidden forwarding header")
        if len(raw_value) > 1024 or any(
            ord(ch) < 32 or ord(ch) > 126 for ch in raw_value
        ):
            raise ValueError("external API header contains unsafe characters")
        headers[name] = raw_value
    return headers


def _bounded_request_data(value: Any, *, kind: str) -> Any:
    """Bound depth, elements and bytes *before* JSON serialization."""
    if value is None:
        return None
    if kind == "params" and (
        type(value) is not dict
        or len(value) > 24
        or any(
            type(key) is not str or not 1 <= len(key) <= 64
            or type(item) not in (str, int, float, bool)
            or (type(item) is str and len(item) > 1024)
            or (type(item) is float and not math.isfinite(item))
            for key, item in value.items()
        )
    ):
        raise ValueError("external API query parameters are invalid")

    remaining = _MAX_EXTERNAL_REQUEST_BYTES
    visited = 0

    def admit(node: Any, depth: int) -> None:
        nonlocal remaining, visited
        visited += 1
        if visited > 512 or depth > 6:
            raise ValueError("external API request exceeds node/depth budget")
        if node is None or type(node) is bool:
            remaining -= 5
        elif type(node) is str:
            if len(node) > _MAX_EXTERNAL_REQUEST_BYTES:
                raise ValueError("external API string exceeds the byte budget")
            remaining -= len(node.encode("utf-8"))
        elif type(node) in (int, float):
            if type(node) is float and not math.isfinite(node):
                raise ValueError("external API request contains nonfinite number")
            # Large integers cannot bypass the output budget via formatting.
            if len(str(node)) > 64:
                raise ValueError("external API number exceeds the byte budget")
            remaining -= 64
        elif type(node) is list:
            if len(node) > 64:
                raise ValueError("external API list exceeds element budget")
            remaining -= len(node) * 2
            for child in node:
                admit(child, depth + 1)
        elif type(node) is dict:
            if len(node) > 64:
                raise ValueError("external API object exceeds key budget")
            remaining -= len(node) * 4
            for key, child in node.items():
                if type(key) is not str or len(key) > 128:
                    raise ValueError("external API object contains invalid key")
                admit(key, depth + 1)
                admit(child, depth + 1)
        else:
            raise ValueError("external API request contains invalid type")
        if remaining < 0:
            raise ValueError("external API request exceeds byte budget")

    admit(value, 0)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > _MAX_EXTERNAL_REQUEST_BYTES:
        raise ValueError("external API request exceeds byte budget")
    return value


async def _bounded_external_body(response: Any) -> str:
    """Stream with a hard memory budget, never use unbounded response.text."""
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except (ValueError, TypeError) as exc:
            raise ValueError("external API content length is invalid") from exc
        if not 0 <= declared_size <= _MAX_EXTERNAL_RESPONSE_BYTES:
            raise ValueError("external API response exceeds the byte budget")
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > _MAX_EXTERNAL_RESPONSE_BYTES:
            raise ValueError("external API response exceeds the byte budget")
        body.extend(chunk)
    return body.decode("utf-8", errors="replace")[:2000]

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
    """Call only approved public endpoints with bounded DNS, body and response."""
    if not isinstance(target, dict):
        return {"channel": "api", "target": "external-api",
                "ok": False, "error": "invalid_api_target"}
    name = target.get("name")
    if type(name) is not str or not 1 <= len(name) <= 64 or not all(
        ch.isascii() and (ch.isalnum() or ch in "-_") for ch in name
    ):
        name = "external-api"
    if not _EXTERNAL_ENABLED:
        return {"channel": "api", "target": name, "ok": True, "disabled": True,
                "note": "external APIs disabled by default"}
    try:
        url = target.get("url", "")
        # The compatibility validator includes a DNS lookup. Keep both checks
        # off the event loop with bounded admission timeouts.
        base_url, request_target = await asyncio.wait_for(
            asyncio.to_thread(_prepare_external_request, url), timeout=5.0
        )
        method = _safe_method(target.get("method", "GET"))
        timeout = _safe_timeout(target.get("timeout", 8))
        headers = _safe_headers(target.get("headers")) or {}
        params = _bounded_request_data(target.get("params"), kind="params")
        payload = _bounded_request_data(target.get("json"), kind="json")
        hostname = urlsplit(base_url).hostname
        if hostname is None:
            raise ValueError("external API host is missing")
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
                params=params,
                headers=headers,
                json=payload,
                extensions={"sni_hostname": hostname},
            ) as response:
                body = await _bounded_external_body(response)
                return {"channel": "api", "target": name,
                        "ok": response.is_success,
                        "status": response.status_code, "body": body}
    except Exception:  # noqa: BLE001
        return {"channel": "api", "target": name,
                "ok": False, "error": "api_query_failed"}

async def query_concurrent(room_id: str, mcp_queries: list[str] | None = None,
                           api_targets: list[dict] | None = None,
                           sources: list[str] | None = None) -> dict:
    """Bound one room's MCP/API fan-out and total in-flight work.

    Large workloads must be split into admitted batches. This prevents a
    single untrusted room request from spawning thousands of DNS operations,
    HTTP streams or blocking thread-pool calls.
    """
    if type(room_id) is not str or not 1 <= len(room_id) <= 128:
        raise ValueError("room_id must be a bounded string")
    mcp_queries = [] if mcp_queries is None else mcp_queries
    api_targets = [] if api_targets is None else api_targets
    if (
        type(mcp_queries) is not list
        or len(mcp_queries) > _MAX_MCP_QUERIES_PER_CALL
        or any(type(q) is not str or not 1 <= len(q) <= 2048 for q in mcp_queries)
        or type(api_targets) is not list
        or len(api_targets) > _MAX_EXTERNAL_TARGETS_PER_CALL
        or any(not isinstance(item, dict) for item in api_targets)
        or len(mcp_queries) + len(api_targets) > _MAX_TOTAL_CONCURRENT_JOBS
        or (
            sources is not None
            and (
                type(sources) is not list or len(sources) > 16
                or any(type(s) is not str or not 1 <= len(s) <= 100 for s in sources)
            )
        )
    ):
        raise ValueError("room query exceeds admission bounds")

    t0 = time.perf_counter()
    capacity = asyncio.Semaphore(_MAX_INFLIGHT_PER_CALL)

    async def admitted(coroutine):
        async with capacity:
            return await coroutine

    tasks = [admitted(_mcp_query(q, sources)) for q in mcp_queries]
    tasks.extend(admitted(_api_query(item)) for item in api_targets)
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
