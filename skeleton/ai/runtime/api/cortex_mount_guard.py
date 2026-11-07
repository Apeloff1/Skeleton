"""Fail-closed protection against HTTP mounting of the cortex route module.

The historical ``cortex_routes.register_routes`` module contains about 52
unchartered endpoints (secrets read/write/rotate, config, flags, policy
rollback, schema, audit, repair, ...). None of them may be served. The app
factory checks the assembled route graph before returning, and
``CortexRouteGuardMiddleware`` (installed by ``create_app`` by default)
re-checks at lifespan startup and whenever the route graph changes, so
routes added later, at any nesting depth, are covered too. This is defense in
depth, not a substitute for handler-level authorization.

Fail-closed rules (TD security review of #4129):

1. Only known route types are inspected (``_IncludedRouter`` first, then
   ``APIRoute``/``APIWebSocketRoute``, Starlette ``Route``/``WebSocketRoute``/
   ``Mount``/``Host``, FastAPI frontend groups). A subclass that overrides
   ``matches`` and every other object, with or without a ``path``, refuses.
2. An opaque mount (no route table) refuses when its prefix could reach a
   secrets path: the root, a prefix of ``/api/v1/secrets``, or any
   path-parameter segment such as ``/{tenant}``. Other opaque mounts are only
   accepted for static-file apps.
3. Cortex is refused by handler identity (``endpoint.__module__``) at any
   prefix, and ``/api/v1/secrets`` is refused anywhere in a composed path.
4. Paths are percent-decoded (repeatedly), NFKC-normalized and casefolded,
   and dot segments are resolved. A registered path containing a dot segment
   (``.``/``..``, including ``%2e`` forms) refuses outright.
5. ``_low_priority_routes`` is walked on every router.
6. A cycle in the route graph refuses; so does depth beyond 32.
"""

from __future__ import annotations

import inspect
import unicodedata
from urllib.parse import unquote

_SECRETS_SEGMENTS = ("api", "v1", "secrets")
_CORTEX_MODULES = frozenset({
    "skeleton.api.cortex_routes",
    "skeleton.ai.runtime.api.cortex_routes",
})
_MAX_DEPTH = 32
_UNINSPECTABLE = "uninspectable HTTP route; refusing startup"
_SECRETS_ERROR = (
    "unchartered cortex secrets HTTP route is forbidden: keep cortex_routes unmounted"
)
_CORTEX_ERROR = "unchartered cortex HTTP route is forbidden: keep cortex_routes unmounted"
_DOT_ERROR = "non-canonical HTTP route path (dot segment); refusing startup"


class _Kinds:
    """Known route classes, resolved lazily so the module imports without FastAPI."""

    _cache: dict | None = None

    @classmethod
    def get(cls) -> dict:
        if cls._cache is None:
            from starlette import routing as sr
            kinds: dict = {"leaf": [sr.Route, sr.WebSocketRoute], "mount": [sr.Mount],
                           "host": [sr.Host], "included": [], "frontend": [], "static": []}
            try:
                from starlette.staticfiles import StaticFiles
                kinds["static"].append(StaticFiles)
            except Exception:  # pragma: no cover - optional dependency
                pass
            try:
                from fastapi import routing as fr
                kinds["leaf"][:0] = [fr.APIRoute, fr.APIWebSocketRoute]
                for name, slot in (("_IncludedRouter", "included"),
                                   ("_FrontendRouteGroup", "frontend"),
                                   ("_FrontendStaticFiles", "static")):
                    found = getattr(fr, name, None)
                    if isinstance(found, type):
                        kinds[slot].append(found)
            except Exception:  # pragma: no cover - FastAPI absent
                pass
            cls._cache = kinds
        return cls._cache


def _kind(route: object) -> str | None:
    """Dispatch on an isinstance allowlist; ``_IncludedRouter`` is checked first."""
    kinds = _Kinds.get()
    for slot in ("included", "leaf", "mount", "host", "frontend"):
        for base in kinds[slot]:
            if isinstance(route, base):
                # A subclass that re-implements matching is not a known type.
                if type(route).matches is not base.matches:
                    return None
                return slot
    return None


def _join(prefix: str, path: str) -> str:
    left = prefix.rstrip("/")
    right = path if not path or path.startswith("/") else f"/{path}"
    if not left:
        return right or "/"
    if not right or right == "/":
        return left or "/"
    return left + right


def _decode(path: str) -> str:
    decoded = path
    for _ in range(4):
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    return unicodedata.normalize("NFKC", decoded).casefold()


def _raw_segments(path: str) -> list[str]:
    # Backslashes are treated as separators by some ingress stacks.
    return _decode(path).replace("\\", "/").split("/")


def _has_dot_segment(path: str) -> bool:
    return any(segment in (".", "..") for segment in _raw_segments(path))


def _segments(path: str) -> list[str]:
    """Decoded, NFKC/casefolded segments with ``//``, ``.`` and ``..`` resolved."""
    out: list[str] = []
    for segment in _raw_segments(path):
        if segment in ("", "."):
            continue
        if segment == "..":
            if out:
                out.pop()
            continue
        out.append(segment)
    return out


def _normalize(path: str) -> str:
    return "/" + "/".join(_segments(path))


def _contains_secrets(segments: list[str]) -> bool:
    n = len(_SECRETS_SEGMENTS)
    return any(tuple(segments[i:i + n]) == _SECRETS_SEGMENTS
               for i in range(len(segments) - n + 1))


def _is_secrets(path: str) -> bool:
    return _contains_secrets(_segments(path))


def _could_reach_secrets(prefix: str) -> bool:
    """True when an opaque app mounted at ``prefix`` could serve a secrets path."""
    segments = _segments(prefix)
    if not segments or any("{" in segment for segment in segments):
        return True
    if _contains_secrets(segments):
        return True
    return tuple(segments) == _SECRETS_SEGMENTS[:len(segments)]


def _module_of(obj: object) -> str:
    try:
        target = inspect.unwrap(obj) if callable(obj) else obj
    except Exception:
        target = obj
    module = getattr(target, "__module__", None)
    if not isinstance(module, str):
        module = getattr(type(target), "__module__", "") or ""
    return module


def _is_cortex(obj: object) -> bool:
    return _module_of(obj) in _CORTEX_MODULES or (
        getattr(type(obj), "__module__", "") in _CORTEX_MODULES
    )


def _tables(obj: object) -> list | None:
    """Route lists of a router/app: ``routes`` plus ``_low_priority_routes``."""
    holder = obj
    if not isinstance(getattr(obj, "routes", None), (list, tuple)):
        holder = getattr(obj, "router", None)
    elif isinstance(getattr(getattr(obj, "router", None), "routes", None), (list, tuple)):
        holder = obj.router  # FastAPI/Starlette app: low-priority routes live on the router
    if holder is None:
        return None
    routes = getattr(holder, "routes", None)
    if routes is None:
        return None
    if not isinstance(routes, (list, tuple)):
        raise RuntimeError(_UNINSPECTABLE)
    tables = [routes]
    low = getattr(holder, "_low_priority_routes", None)
    if low is not None:
        if not isinstance(low, (list, tuple)):
            raise RuntimeError(_UNINSPECTABLE)
        tables.append(low)
    return tables


def _check_opaque(prefix: str, app: object) -> None:
    if _is_cortex(app) or _could_reach_secrets(prefix):
        raise RuntimeError(_UNINSPECTABLE)
    if not any(isinstance(app, base) for base in _Kinds.get()["static"]):
        raise RuntimeError(_UNINSPECTABLE)


def _walk_tables(tables: list, prefix: str, stack: tuple[int, ...]):
    for table in tables:
        if id(table) in stack:
            raise RuntimeError(_UNINSPECTABLE)  # cycle
        yield from _iter_paths(table, prefix, stack + (id(table),))


def _iter_paths(routes: object, prefix: str, stack: tuple[int, ...]):
    if not isinstance(routes, (list, tuple)):
        raise RuntimeError(_UNINSPECTABLE)
    if len(stack) > 2 * _MAX_DEPTH:
        raise RuntimeError(_UNINSPECTABLE)
    for route in routes:
        marker = id(route)
        if marker in stack:  # cycle: fail closed (same router at two prefixes is not a cycle)
            raise RuntimeError(_UNINSPECTABLE)
        here = stack + (marker,)
        kind = _kind(route)
        if kind == "included":
            original = getattr(route, "original_router", None)
            context = getattr(route, "include_context", None)
            extra = getattr(context, "prefix", None)
            if original is None or not isinstance(extra, str):
                raise RuntimeError(_UNINSPECTABLE)
            if id(original) in stack:
                raise RuntimeError(_UNINSPECTABLE)
            tables = _tables(original)
            if tables is None:
                raise RuntimeError(_UNINSPECTABLE)
            yield from _walk_tables(tables, _join(prefix, extra), here + (id(original),))
            continue
        if kind in ("leaf", "mount", "frontend"):
            path = getattr(route, "path", "" if kind == "frontend" else None)
            if not isinstance(path, str):
                raise RuntimeError(_UNINSPECTABLE)
            if _has_dot_segment(path):
                raise RuntimeError(_DOT_ERROR)
            full = _join(prefix, path)
            if kind == "leaf":
                if _is_cortex(getattr(route, "endpoint", None)):
                    raise RuntimeError(_CORTEX_ERROR)
                yield full
                continue
            if kind == "frontend":
                for child in getattr(route, "routes", None) or []:
                    child_path = getattr(child, "path", None)
                    if not isinstance(child_path, str):
                        raise RuntimeError(_UNINSPECTABLE)
                    child_full = _join(full, child_path)
                    _check_opaque(child_full, getattr(child, "app", None))
                    yield child_full
                continue
            # Mount: walk its sub-routes or sub-application; opaque apps refuse
            # unless static files at a prefix that cannot reach secrets.
            yield full
            base = getattr(route, "_base_app", None) or getattr(route, "app", None)
            if _is_cortex(base):
                raise RuntimeError(_CORTEX_ERROR)
            if id(base) in stack:
                raise RuntimeError(_UNINSPECTABLE)
            tables = _tables(base)
            if tables is None:
                _check_opaque(full, base)
                continue
            yield from _walk_tables(tables, full, here + (id(base),))
            continue
        if kind == "host":
            base = getattr(route, "app", None)
            if id(base) in stack:
                raise RuntimeError(_UNINSPECTABLE)
            tables = _tables(base)
            if tables is None:
                raise RuntimeError(_UNINSPECTABLE)
            yield from _walk_tables(tables, prefix, here + (id(base),))
            continue
        raise RuntimeError(_UNINSPECTABLE)  # unknown route type, with or without .path


def iter_route_paths(app: object) -> list[str]:
    """All composed paths of ``app`` (HTTP, WebSocket, low-priority). Raises if uninspectable."""
    try:
        tables = _tables(app)
    except RuntimeError:
        raise
    if tables is None:
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    return list(_walk_tables(tables, "", (id(app),)))


def reject_cortex_secret_routes(app: object) -> None:
    """Refuse app startup if any registered route is cortex or reaches cortex secrets."""
    for path in iter_route_paths(app):
        if _is_secrets(path):
            raise RuntimeError(_SECRETS_ERROR)


def _fingerprint(obj: object, seen: set[int], out: list, depth: int = 0) -> None:
    """Cheap structural signature of the whole route graph (ids + lengths)."""
    if depth > 2 * _MAX_DEPTH or id(obj) in seen:
        out.append(("cycle-or-deep", id(obj)))
        return
    seen.add(id(obj))
    for name in ("routes", "_low_priority_routes"):
        table = getattr(obj, name, None)
        if isinstance(table, (list, tuple)):
            out.append((name, id(table), len(table)))
            for route in table:
                out.append(id(route))
                for child in (getattr(route, "original_router", None),
                              getattr(route, "_base_app", None), getattr(route, "app", None)):
                    if child is not None and child is not route:
                        _fingerprint(child, seen, out, depth + 1)
    router = getattr(obj, "router", None)
    if router is not None and router is not obj:
        _fingerprint(router, seen, out, depth + 1)


class CortexRouteGuardMiddleware:
    """Re-check the route graph at lifespan startup and whenever it changes.

    ``create_app`` installs it by default:
    ``app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)``.
    The graph signature covers nested additions and same-length swaps at any
    depth. Any exception while checking is a violation: startup fails and
    HTTP/WebSocket requests are refused (503 / close 1011).
    """

    def __init__(self, app, *, guarded_app: object) -> None:
        self.app = app
        self.guarded_app = guarded_app
        self._signature: object = None
        self._error: str | None = None

    def _signature_now(self) -> object:
        out: list = []
        version = getattr(getattr(self.guarded_app, "router", None), "_get_routes_version", None)
        try:
            out.append(version() if callable(version) else None)
            _fingerprint(self.guarded_app, set(), out)
        except Exception as exc:  # signature failure is itself a violation
            return ("error", repr(exc), object())
        return tuple(out)

    def _check(self, force: bool = False) -> None:
        signature = self._signature_now()
        if not force and signature == self._signature and self._error is None:
            return
        try:
            reject_cortex_secret_routes(self.guarded_app)
            self._error = None
        except Exception as exc:  # fail closed on anything, not just RuntimeError
            self._error = str(exc) or type(exc).__name__
        self._signature = signature

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        self._check(force=kind == "lifespan")
        if self._error is None:
            await self.app(scope, receive, send)
            return
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
