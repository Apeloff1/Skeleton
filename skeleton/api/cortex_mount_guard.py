"""Fail-closed protection against accidental HTTP mounting of cortex routes.

The historical ``cortex_routes.register_routes`` module holds about 52
unchartered endpoints (secrets read/write/rotate, config, flags, policy
rollback, schema, repair, ...). None may be served. This guard is
defense in depth, not a substitute for handler-level authorization.

Fail-closed contract (Jenkins #4129 review, blockers B1-B7):

* B1  Only known route types are accepted: FastAPI ``APIRoute`` /
      ``APIWebSocketRoute``, Starlette ``Route`` / ``WebSocketRoute`` /
      ``Mount`` / ``Host`` and FastAPI's lazy ``_IncludedRouter`` (>= 0.141,
      unwrapped via ``original_router`` + ``include_context.prefix``).
      Anything else raises, whatever attributes it exposes.
* B2  Opaque mounts (an ASGI app with no route table) are refused at any
      prefix, including parameter prefixes such as ``/{tenant}``. Only
      ``StaticFiles`` at a literal prefix is allowed.
* B3  Any endpoint defined in a cortex_routes module is refused at ANY
      prefix (identity beats spelling); ``/api/v1/secrets`` is also matched
      as a segment sequence anywhere in the composed path.
* B4  Paths are NFKC-normalized, percent-decoded to a fixed point, casefolded
      and separator-collapsed; any ``.``/``..`` segment (incl. ``%2e``) is
      refused outright.
* B5  ``CortexRouteGuardMiddleware`` is installed by ``create_app`` and
      re-walks the whole graph at lifespan startup and on every request, so
      nested or late additions to live included routers are caught. Any
      exception during the walk is a violation.
* B6  ``_low_priority_routes`` (e.g. ``frontend()`` groups) is walked on every
      router; entries outside the allowlist raise.
* B7  A cycle in the route graph raises.
"""

from __future__ import annotations

import posixpath
import unicodedata
from urllib.parse import unquote

from starlette.routing import Host, Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

try:  # FastAPI is optional for pure-Starlette callers.
    from fastapi import routing as _fr
    _API_LEAVES: tuple[type, ...] = (_fr.APIRoute, _fr.APIWebSocketRoute)
    _INCLUDED = getattr(_fr, "_IncludedRouter", None)
except Exception:  # noqa: BLE001  # pragma: no cover - FastAPI always installed
    _API_LEAVES = ()
    _INCLUDED = None

_SECRETS = ("api", "v1", "secrets")
_CORTEX_MODULES = frozenset({
    "skeleton.api.cortex_routes",
    "skeleton.ai.runtime.api.cortex_routes",
})
_MAX_DEPTH = 32
_UNINSPECTABLE = "uninspectable HTTP route; refusing startup"
_LEAVES: tuple[type, ...] = _API_LEAVES + (Route, WebSocketRoute)


def _join(prefix: str, path: str) -> str:
    left = prefix.rstrip("/")
    right = path if not path or path.startswith("/") else f"/{path}"
    if not left:
        return right or "/"
    if not right or right == "/":
        return left or "/"
    return left + right


def _segments(path: str) -> list[str]:
    """Canonical segments; refuses dot segments and unstable encodings."""
    if not isinstance(path, str):
        raise RuntimeError(_UNINSPECTABLE)
    decoded = unicodedata.normalize("NFKC", path)
    for _ in range(4):
        expanded = unicodedata.normalize("NFKC", unquote(decoded))
        if expanded == decoded:
            break
        decoded = expanded
    else:
        raise RuntimeError(_UNINSPECTABLE + " (unstable percent-encoding)")
    decoded = decoded.replace("\\", "/").casefold()
    parts = decoded.split("/")
    if any(part in (".", "..") for part in parts):
        raise RuntimeError(_UNINSPECTABLE + " (dot segment in route path)")
    segments = [part for part in parts if part]
    if posixpath.normpath("/" + "/".join(segments)) != "/" + "/".join(segments) and segments:
        raise RuntimeError(_UNINSPECTABLE)  # pragma: no cover - defensive
    return segments


def _normalize(path: str) -> str:
    return "/" + "/".join(_segments(path))


def _is_secrets(path: str) -> bool:
    segs = _segments(path)
    n = len(_SECRETS)
    return any(tuple(segs[i:i + n]) == _SECRETS for i in range(len(segs) - n + 1))


def _reject_secret_path(path: str) -> None:
    if _is_secrets(path):
        raise RuntimeError(
            "unchartered cortex secrets HTTP route is forbidden: "
            "keep cortex_routes unmounted"
        )


def _reject_cortex_endpoint(route: object, path: str) -> None:
    endpoint = getattr(route, "endpoint", None)
    seen = 0
    while endpoint is not None and seen < 16:
        if getattr(endpoint, "__module__", None) in _CORTEX_MODULES:
            raise RuntimeError(
                f"unchartered cortex HTTP route is forbidden ({path}): "
                "keep cortex_routes unmounted"
            )
        endpoint = getattr(endpoint, "__wrapped__", None)
        seen += 1


def _app_tables(obj: object) -> list[object] | None:
    """Route lists of an app/router: ``routes`` then ``_low_priority_routes``."""
    router = obj
    routes = getattr(obj, "routes", None)
    if not isinstance(routes, (list, tuple)):
        router = getattr(obj, "router", None)
        routes = getattr(router, "routes", None) if router is not None else None
    if not isinstance(routes, (list, tuple)):
        return None
    tables: list[object] = [routes]
    low = getattr(router, "_low_priority_routes", None)
    if low is None and router is obj:
        inner = getattr(obj, "router", None)
        low = getattr(inner, "_low_priority_routes", None) if inner is not None else None
    if low is not None:
        if not isinstance(low, (list, tuple)):
            raise RuntimeError(_UNINSPECTABLE)
        tables.append(low)
    return tables


def _walk_tables(tables, prefix: str, stack: tuple[int, ...]):
    for table in tables:
        yield from _iter_paths(table, prefix, stack)


def _iter_paths(routes: object, prefix: str, stack: tuple[int, ...]):
    if not isinstance(routes, (list, tuple)):
        raise RuntimeError(_UNINSPECTABLE)
    if len(stack) > _MAX_DEPTH:
        raise RuntimeError(_UNINSPECTABLE + " (route graph too deep)")
    for route in routes:
        marker = id(route)
        if marker in stack:
            raise RuntimeError(_UNINSPECTABLE + " (cycle in route graph)")
        here = stack + (marker,)
        if _INCLUDED is not None and isinstance(route, _INCLUDED):
            context = getattr(route, "include_context", None)
            extra = getattr(context, "prefix", None)
            original = getattr(route, "original_router", None)
            if not isinstance(extra, str) or original is None:
                raise RuntimeError(_UNINSPECTABLE)
            if id(original) in stack:
                raise RuntimeError(_UNINSPECTABLE + " (cycle in route graph)")
            tables = _app_tables(original)
            if tables is None:
                raise RuntimeError(_UNINSPECTABLE)
            yield from _walk_tables(tables, _join(prefix, extra), here + (id(original),))
            continue
        if isinstance(route, _LEAVES):
            path = getattr(route, "path", None)
            if not isinstance(path, str):
                raise RuntimeError(_UNINSPECTABLE)  # noqa: TRY004
            full = _join(prefix, path)
            _reject_cortex_endpoint(route, full)
            yield full
            continue
        if isinstance(route, Mount):
            path = getattr(route, "path", None)
            if not isinstance(path, str):
                raise RuntimeError(_UNINSPECTABLE)  # noqa: TRY004
            full = _join(prefix, path)
            yield full
            base = getattr(route, "_base_app", None) or getattr(route, "app", None)
            if id(base) in stack:
                raise RuntimeError(_UNINSPECTABLE + " (cycle in route graph)")
            tables = _app_tables(base)
            if tables is None:
                if isinstance(base, StaticFiles) and "{" not in full:
                    continue
                raise RuntimeError(_UNINSPECTABLE + f" (opaque mount at {full})")
            yield from _walk_tables(tables, full, here + (id(base),))
            continue
        if isinstance(route, Host):
            base = getattr(route, "app", None)
            if id(base) in stack:
                raise RuntimeError(_UNINSPECTABLE + " (cycle in route graph)")
            tables = _app_tables(base)
            if tables is None:
                raise RuntimeError(_UNINSPECTABLE + " (opaque host)")
            yield from _walk_tables(tables, prefix, here + (id(base),))
            continue
        raise RuntimeError(_UNINSPECTABLE + f" (unknown route type {type(route).__qualname__})")


def iter_route_paths(app: object) -> list[str]:
    """All composed paths of ``app`` (HTTP and WebSocket). Raises if uninspectable."""
    tables = _app_tables(app)
    if tables is None:
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    return list(_walk_tables(tables, "", (id(app),)))


def reject_cortex_secret_routes(app: object) -> None:
    """Refuse startup if any route is a cortex handler or reaches cortex secrets."""
    for path in iter_route_paths(app):
        _reject_secret_path(path)


class CortexRouteGuardMiddleware:
    """Full re-walk at lifespan startup and on every HTTP/WebSocket request.

    Installed by default in ``create_app``. Any exception while walking counts
    as a violation: startup fails, HTTP gets 503, WebSocket is closed (1011).
    """

    def __init__(self, app, *, guarded_app: object) -> None:
        self.app = app
        self.guarded_app = guarded_app

    def _violation(self) -> str | None:
        try:
            reject_cortex_secret_routes(self.guarded_app)
        except Exception as exc:  # noqa: BLE001 - fail closed on anything
            return str(exc) or type(exc).__name__
        return None

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind == "lifespan":
            error = self._violation()
            if error is None:
                await self.app(scope, receive, send)
                return
            message = await receive()
            if message.get("type") == "lifespan.startup":
                await send({"type": "lifespan.startup.failed", "message": error})
            # Mirror Starlette's Router.lifespan: surface the failure to the server.
            raise RuntimeError(error)
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if self._violation() is None:
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1011})
            return
        body = b'{"error":"route_guard_violation"}'
        await send({"type": "http.response.start", "status": 503,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


__all__ = ["CortexRouteGuardMiddleware", "iter_route_paths", "reject_cortex_secret_routes"]
