"""Fail-closed protection against accidental HTTP mounting of cortex secrets.

The historical cortex_routes.register_routes module contains unchartered
read/write/rotate secrets endpoints and MUST remain unmounted. The app factory
checks the assembled route table before returning an ASGI application; this
is a defense-in-depth guard, not a substitute for handler-level authorization.

FastAPI stores included routers as ``_IncludedRouter`` entries that have no
string path of their own. The guard walks those entries, and Starlette mounts,
and still refuses any route whose path cannot be inspected.
"""

from __future__ import annotations

from urllib.parse import unquote


def _join(prefix: str, path: str) -> str:
    left = prefix.rstrip("/")
    right = path if not path or path.startswith("/") else f"/{path}"
    if not left:
        return right or "/"
    if not right or right == "/":
        return left
    return left + right


def _normalize(path: str) -> str:
    decoded = path
    for _ in range(3):
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    return "/" + "/".join(segment for segment in decoded.casefold().split("/") if segment)


def _iter_paths(routes: object, prefix: str, seen: set[int]) -> list[str]:
    if not isinstance(routes, (list, tuple)):
        raise RuntimeError("uninspectable HTTP route; refusing startup")
    found: list[str] = []
    for route in routes:
        marker = id(route)
        if marker in seen:
            continue
        seen.add(marker)
        path = getattr(route, "path", None)
        original = getattr(route, "original_router", None)
        if isinstance(path, str):
            found.append(_join(prefix, path))
            children = getattr(route, "routes", None)
            if children:
                found.extend(_iter_paths(children, _join(prefix, path), seen))
            continue
        if original is not None:
            context = getattr(route, "include_context", None)
            extra = getattr(context, "prefix", "") if context is not None else ""
            child_prefix = _join(prefix, extra) if isinstance(extra, str) and extra else prefix
            children = getattr(original, "routes", None)
            found.extend(_iter_paths(children, child_prefix, seen))
            continue
        children = getattr(route, "routes", None)
        if children:
            found.extend(_iter_paths(children, prefix, seen))
            continue
        raise RuntimeError("uninspectable HTTP route; refusing startup")
    return found


def reject_cortex_secret_routes(app: object) -> None:
    """Refuse app startup if a registered HTTP path exposes cortex secrets."""

    routes = getattr(app, "routes", None)
    if routes is None:
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    for path in _iter_paths(routes, "", set()):
        normalized = _normalize(path)
        if normalized == "/api/v1/secrets" or normalized.startswith("/api/v1/secrets/"):
            raise RuntimeError(
                "unchartered cortex secrets HTTP route is forbidden: "
                "keep cortex_routes unmounted"
            )


__all__ = ["reject_cortex_secret_routes"]
