"""Fail-closed protection against accidental HTTP mounting of cortex secrets.

The historical cortex_routes.register_routes module contains unchartered
read/write/rotate secrets endpoints and MUST remain unmounted. The app factory
checks the assembled route table before returning an ASGI application; this
is a defense-in-depth guard, not a substitute for handler-level authorization.
"""
from __future__ import annotations

from urllib.parse import unquote


def _iter_route_paths(routes, prefix: str = "", depth: int = 0):
    """Yield full paths, expanding FastAPI>=0.141 lazy ``_IncludedRouter`` entries.

    Fail-closed: anything that is neither a pathed route nor an included router
    with an inspectable prefix and route list aborts startup.
    """
    if depth > 16:
        raise RuntimeError("uninspectable HTTP route; refusing startup")
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            yield prefix + path
            continue
        original = getattr(route, "original_router", None)
        context = getattr(route, "include_context", None)
        inner_prefix = getattr(context, "prefix", None)
        inner_routes = getattr(original, "routes", None)
        if original is None or not isinstance(inner_prefix, str) or inner_routes is None:
            raise RuntimeError("uninspectable HTTP route; refusing startup")
        yield from _iter_route_paths(inner_routes, prefix + inner_prefix, depth + 1)


def reject_cortex_secret_routes(app: object) -> None:
    """Refuse app startup if a registered HTTP path exposes cortex secrets."""
    routes = getattr(app, "routes", None)
    if routes is None:
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    for path in _iter_route_paths(routes):
        # Starlette provides decoded ASGI paths; also inspect percent-encoded
        # aliases so registration spelling cannot bypass the source guard.
        decoded = path
        for _ in range(3):
            expanded = unquote(decoded)
            if expanded == decoded:
                break
            decoded = expanded
        # Multiple separators are normalized by some ingress stacks, so do
        # not let an alias slip past before the request reaches Starlette.
        normalized = "/" + "/".join(
            segment for segment in decoded.casefold().split("/") if segment
        )
        if normalized == "/api/v1/secrets" or normalized.startswith("/api/v1/secrets/"):
            raise RuntimeError(
                "unchartered cortex secrets HTTP route is forbidden: "
                "keep cortex_routes unmounted"
            )


__all__ = ["reject_cortex_secret_routes"]
