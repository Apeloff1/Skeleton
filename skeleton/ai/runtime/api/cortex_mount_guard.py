"""Staged mirror of the canonical cortex secrets mount guard.

The historical cortex_routes.register_routes module contains unchartered
read/write/rotate secrets endpoints and MUST remain unmounted. The app factory
checks the assembled route table before returning an ASGI application; this
is a defense-in-depth guard, not a substitute for handler-level authorization.

FastAPI >= 0.141 stores ``include_router`` results as lazy ``_IncludedRouter``
entries with no string ``path``. The guard expands them (at any depth, composing
prefixes), walks Starlette ``Mount``/``Host`` sub-routes and sub-applications,
covers HTTP and WebSocket routes alike, and refuses startup on anything it
cannot inspect. An opaque mount (an ASGI app without a route table) is refused
when its prefix could reach ``/api/v1/secrets``. ``CortexRouteGuardMiddleware``
re-runs the check at ASGI startup and whenever the route table grows, so routes
added after ``create_app`` returns are covered too.
"""
from __future__ import annotations
from urllib.parse import unquote
_SECRETS = "/api/v1/secrets"
_MAX_DEPTH = 32
_UNINSPECTABLE = "uninspectable HTTP route; refusing startup"
def _join(prefix: str, path: str) -> str:
    left = prefix.rstrip("/")
    right = path if not path or path.startswith("/") else f"/{path}"
    if not left:
        return right or "/"
    if not right or right == "/":
        return left or "/"
    return left + right
def _normalize(path: str) -> str:
    decoded = path
    for _ in range(3):
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    # Multiple separators are normalized by some ingress stacks, so do not let
    # an alias slip past before the request reaches Starlette.
    return "/" + "/".join(segment for segment in decoded.casefold().split("/") if segment)
def _is_secrets(path: str) -> bool:
    normalized = _normalize(path)
    return normalized == _SECRETS or normalized.startswith(_SECRETS + "/")
def _could_reach_secrets(prefix: str) -> bool:
    """True when an opaque app mounted at ``prefix`` could serve the secrets path."""
    normalized = _normalize(prefix)
    return normalized == "/" or _SECRETS == normalized or _SECRETS.startswith(normalized + "/") \
        or normalized.startswith(_SECRETS + "/")
def _route_table(obj: object):
    routes = getattr(obj, "routes", None)
    if routes is None:
        inner = getattr(obj, "router", None)  # FastAPI/Starlette app -> router.routes
        routes = getattr(inner, "routes", None) if inner is not None else None
    return routes
def _iter_paths(routes: object, prefix: str, stack: tuple[int, ...]):
    if not isinstance(routes, (list, tuple)):
        raise RuntimeError(_UNINSPECTABLE)
    if len(stack) > _MAX_DEPTH:
    for route in routes:
        marker = id(route)
        if marker in stack:  # true cycle only; the same router at two prefixes is walked twice
            continue
        here = stack + (marker,)
        path = getattr(route, "path", None)
        original = getattr(route, "original_router", None)
        if isinstance(path, str):
            full = _join(prefix, path)
            yield full
            if hasattr(route, "app") and not hasattr(route, "endpoint"):
                # Mount / Host style: walk its sub-routes or sub-application.
                # Mount.routes returns [] for opaque apps, so inspect the base app itself.
                base = getattr(route, "_base_app", None) or getattr(route, "app", None)
                children = _route_table(base)
                if children is None:
                    if _could_reach_secrets(full):
                        raise RuntimeError(_UNINSPECTABLE)
                    continue
                yield from _iter_paths(children, full, here)
        if original is not None:
            context = getattr(route, "include_context", None)
            extra = getattr(context, "prefix", None) if context is not None else None
            if not isinstance(extra, str):
                raise RuntimeError(_UNINSPECTABLE)
            yield from _iter_paths(getattr(original, "routes", None), _join(prefix, extra), here)
        if isinstance(getattr(route, "host", None), str):
            # Starlette Host: same path space, walk its app's table (opaque -> refuse).
            base = getattr(route, "app", None)
            children = _route_table(base)
            if children is None:
            yield from _iter_paths(children, prefix, here)
def iter_route_paths(app: object) -> list[str]:
    """All composed paths of ``app`` (HTTP and WebSocket). Raises if uninspectable."""
    routes = _route_table(app)
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    return list(_iter_paths(routes, "", ()))
def reject_cortex_secret_routes(app: object) -> None:
    """Refuse app startup if a registered HTTP path exposes cortex secrets."""
    for path in iter_route_paths(app):
        if _is_secrets(path):
            raise RuntimeError(
                "unchartered cortex secrets HTTP route is forbidden: "
                "keep cortex_routes unmounted"
            )
The implementation lives in ``skeleton.api.cortex_mount_guard``. This module
re-exports it so the runtime tree cannot keep a second, older startup check.
from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes

class CortexRouteGuardMiddleware:
    """Re-check the route table at ASGI startup and when it grows (late additions).

    Opt-in hook: ``app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)``.
    On violation, startup fails and HTTP/WebSocket requests are refused (503 / close).
    """

    def __init__(self, app, *, guarded_app: object) -> None:
        self.app = app
        self.guarded_app = guarded_app
        self._checked_len = -1
        self._error: str | None = None

    def _check(self) -> None:
        routes = _route_table(self.guarded_app)
        size = len(routes) if isinstance(routes, (list, tuple)) else -2
        if size == self._checked_len and self._error is None:
            return
        try:
            reject_cortex_secret_routes(self.guarded_app)
            self._error = None
        except RuntimeError as exc:
            self._error = str(exc)
        self._checked_len = size

    async def __call__(self, scope, receive, send):
        self._check()
        if self._error is None:
            await self.app(scope, receive, send)
            return
        kind = scope.get("type")
        if kind == "lifespan":
            message = await receive()
            if message.get("type") == "lifespan.startup":
                await send({"type": "lifespan.startup.failed", "message": self._error})
            return
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1011})
            return
        body = b'{"error":"route_guard_violation"}'
        await send({"type": "http.response.start", "status": 503,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


__all__ = ["CortexRouteGuardMiddleware", "iter_route_paths", "reject_cortex_secret_routes"]
