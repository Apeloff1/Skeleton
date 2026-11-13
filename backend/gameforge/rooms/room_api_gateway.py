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
_MAX_DNS_ANSWERS = 32
_MAX_EXTERNAL_RESPONSE_BYTES = 64 * 1024
_MAX_EXTERNAL_JSON_BYTES = 64 * 1024
_MAX_RESPONSE_BYTES = _MAX_EXTERNAL_RESPONSE_BYTES
_MAX_MCP_QUERIES = _MAX_MCP_FANOUT
_MAX_API_TARGETS = _MAX_API_FANOUT
_MAX_SOURCES = 32
_MAX_CONCURRENT_QUERIES = _MAX_PARALLEL_QUERIES
_MAX_API_FANOUT = 16
_MAX_MCP_FANOUT = 32
_MAX_PARALLEL_QUERIES = 8
_FORBIDDEN_FORWARD_HEADERS = frozenset({
    "host",
    "proxy-authorization",
    "proxy-connection",
    "connection",
    "transfer-encoding",
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "forwarded",
    "x-forwarded-host",
    "x-forwarded-for",
    "x-auth-token",
    "x-real-ip",
    "upgrade",
    "content-length",
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
    if len(addresses) > _MAX_DNS_ANSWERS:
        raise ValueError("external API host returned too many DNS answers")
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
    # Never coerce an attacker-controlled object through __str__.
    if type(value) is not str or not 1 <= len(value) <= 12 or not value.isascii():
        raise ValueError("external API method is invalid")
    method = value.upper()
    if method not in _ALLOWED_HTTP_METHODS:
        raise ValueError("external API method is not allowed")
    return method


def _safe_timeout(value: Any) -> float:
    if type(value) not in (str, int, float) or (type(value) is str and len(value) > 32):
        raise ValueError("external API timeout is invalid")
    try:
        timeout = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("external API timeout is invalid") from exc
    if not math.isfinite(timeout) or timeout <= 0 or timeout > _MAX_EXTERNAL_TIMEOUT_SECONDS:
        raise ValueError("external API timeout is outside the allowed range")
    return timeout


def _safe_headers(value: Any) -> dict[str, str] | None:
    """Validate literal request headers before any network operation."""
    if value is None:
        return None
    if type(value) is not dict or len(value) > 24:
        raise ValueError("external API headers exceed size limits")
    headers: dict[str, str] = {}
    total = 0
    for name, header_value in value.items():
        if (
            type(name) is not str or type(header_value) is not str
            or not 1 <= len(name) <= 64 or not name.isascii()
            or not name[0].isalnum()
            or any(not (ch.isalnum() or ch in "-") for ch in name)
            or name.lower() in _FORBIDDEN_FORWARD_HEADERS
        ):
            raise ValueError("external API contains a forbidden forwarding header")
        if (
            len(header_value) > 1024 or not header_value.isascii()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in header_value)
        ):
            raise ValueError("external API header contains invalid bytes")
        total += len(name) + len(header_value)
        if total > 8192:
            raise ValueError("external API headers exceed aggregate size budget")
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


def _safe_params(params: Any) -> dict[str, str] | None:
    if params is None:
        return None
    if type(params) is not dict or len(params) > 20:
        raise ValueError("external API parameters exceed size limits")
    checked: dict[str, str] = {}
    for key, value in params.items():
        if type(key) is not str or not 1 <= len(key) <= 64 or not key.isascii():
            raise ValueError("external API parameter key is invalid")
        if type(value) not in (str, int, float, bool):
            raise ValueError("external API parameter value has unsupported type")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("external API parameter value must be finite")
        text = str(value)
        if len(text) > 512:
            raise ValueError("external API parameter value exceeds limit")
        checked[key] = text
    return checked


def _bounded_json(value: Any) -> Any:
    """Admission-check a literal JSON tree before allocating its wire encoding.

    Ban custom mappings, recursion, excessive array fanout and nested payloads.
    The caller receives the original literal tree only after every leaf passes.
    """
    if type(value) not in (dict, list):
        raise ValueError("external API JSON request must be a container")
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 1024 or depth > 8:
            raise ValueError("external API JSON exceeds structural budget")
        if type(item) is dict:
            if len(item) > 128:
                raise ValueError("external API JSON exceeds object budget")
            for key, child in item.items():
                if type(key) is not str or not 1 <= len(key) <= 128:
                    raise ValueError("external API JSON key is invalid")
                pending.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > 1024:
                raise ValueError("external API JSON exceeds list budget")
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > _MAX_EXTERNAL_JSON_BYTES:
                raise ValueError("external API JSON exceeds byte budget")
        elif type(item) is int:
            if item.bit_length() > 64:
                raise ValueError("external API JSON integer is unbounded")
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("external API JSON number must be finite")
        elif type(item) not in (bool, type(None)):
            raise ValueError("external API JSON element is unsupported")
    encoded = json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_EXTERNAL_JSON_BYTES:
        raise ValueError("external API JSON exceeds byte budget")
    return value


def _safe_payload(value: Any) -> Any:
    return None if value is None else _bounded_json(value)

async def _bounded_http_body(response) -> str:
    """Stop before consuming an oversized declared or streamed HTTP response."""
    declared = response.headers.get("content-length")
    if declared is not None:
        if type(declared) is not str or not declared.isascii() or not declared.isdecimal():
            raise ValueError("external API response has invalid content length")
        size = int(declared)
        if size > _MAX_RESPONSE_BYTES:
            raise ValueError("external API response exceeds byte budget")
    chunks = bytearray()
    async for chunk in response.aiter_bytes():
        if type(chunk) is not bytes or len(chunks) + len(chunk) > _MAX_RESPONSE_BYTES:
            raise ValueError("external API response exceeds byte budget")
        chunks.extend(chunk)
    return chunks.decode("utf-8", errors="replace")[:2000]


async def _read_external_response(response) -> str:
    """Retained entrypoint for callers that use the bounded reader directly."""
    return await _bounded_http_body(response)

async def _api_query(target: dict) -> dict:
    """Call only a pinned, allowlisted HTTPS endpoint with bounded payload."""
    if type(target) is not dict:
        return {"channel": "api", "target": "invalid", "ok": False,
                "error": "invalid_api_target"}
    url = target.get("url", "")
    # Never echo caller URLs (which may contain tokens) into room responses.
    # A name is only a short ASCII label, not a credential-bearing URI.
    supplied_name = target.get("name", "external_api")
    name = (
        supplied_name
        if type(supplied_name) is str
        and 1 <= len(supplied_name) <= 64
        and supplied_name[0].isascii() and supplied_name[0].isalpha()
        and all(ch.isascii() and (ch.isalnum() or ch in "_-") for ch in supplied_name)
        else "external_api"
    )
    if not _EXTERNAL_ENABLED:
        return {"channel": "api", "target": name, "ok": True, "disabled": True,
                "note": "external APIs disabled (inward-focused); set GAMEFORGE_ENABLE_EXTERNAL_APIS=1"}
    try:
        # DNS resolution runs off the event loop under bounded wait. Double
        # resolution remains fail-closed: both checks reject non-public IPs
        # and the *second* answer is used as the actual socket authority.
        base_url, request_target = await asyncio.wait_for(
            asyncio.to_thread(_prepare_external_request, url), timeout=5.0
        )
        method = _safe_method(target.get("method", "GET"))
        timeout = _safe_timeout(target.get("timeout", 8))
        headers = _safe_headers(target.get("headers")) or {}
        params = _safe_params(target.get("params"))
        payload = _safe_payload(target.get("json"))
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
                body = await _read_external_response(response)
                return {"channel": "api", "target": name, "ok": response.is_success,
                        "status": response.status_code, "body": body}
    except Exception:  # noqa: BLE001
        return {"channel": "api", "target": name, "ok": False, "error": "api_query_failed"}


async def query_concurrent(room_id: str, mcp_queries: list[str] | None = None,
                           api_targets: list[dict] | None = None,
                           sources: list[str] | None = None) -> dict:
    """Fan every MCP query + external API target out CONCURRENTLY for a room.
    Returns per-channel results plus timing so callers can see the parallelism."""
    if (
        type(room_id) is not str or not 1 <= len(room_id) <= 128
        or type(mcp_queries) not in (list, type(None))
        or type(api_targets) not in (list, type(None))
        or type(sources) not in (list, type(None))
    ):
        raise ValueError("room API admission budget rejects invalid argument shapes")
    mcp_queries = mcp_queries or []
    api_targets = api_targets or []
    if (
        len(mcp_queries) > _MAX_MCP_QUERIES
        or len(api_targets) > _MAX_API_TARGETS
        or len(mcp_queries) + len(api_targets) > _MAX_MCP_QUERIES + _MAX_API_TARGETS
        or any(type(q) is not str or not 1 <= len(q) <= 4096 for q in mcp_queries)
        or any(type(t) is not dict for t in api_targets)
        or sources is not None and (
            len(sources) > _MAX_SOURCES
            or any(type(src) is not str or not 1 <= len(src) <= 128 for src in sources)
        )
    ):
        raise ValueError("room API admission budget exceeded")
    t0 = time.perf_counter()
    slots = asyncio.Semaphore(_MAX_PARALLEL_QUERIES)

    async def admitted(coro):
        async with slots:
            return await coro

    tasks = [admitted(_mcp_query(q, sources)) for q in mcp_queries]
    tasks += [admitted(_api_query(t)) for t in api_targets]
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
