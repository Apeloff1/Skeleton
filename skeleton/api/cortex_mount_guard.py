"""Fail-closed protection against accidental HTTP mounting of cortex secrets.

The historical cortex_routes.register_routes module contains unchartered
read/write/rotate secrets endpoints and MUST remain unmounted. The app factory
checks the assembled route table before returning an ASGI application; this
is a defense-in-depth guard, not a substitute for handler-level authorization.
"""
from __future__ import annotations

from urllib.parse import unquote


def reject_cortex_secret_routes(app: object) -> None:
    """Refuse app startup if a registered HTTP path exposes cortex secrets."""
    routes = getattr(app, "routes", None)
    if routes is None or isinstance(routes, (str, bytes)):
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    try:
        pending = list(routes)
    except TypeError as exc:
        raise RuntimeError("HTTP route inventory unavailable; refusing startup") from exc
    seen: set[int] = set()
    while pending:
        route = pending.pop()
        marker = id(route)
        if marker in seen:
            continue
        seen.add(marker)
        path = getattr(route, "path", None)
        if isinstance(path, str):
            _reject_secret_path(path)
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            try:
                nested = candidates()
            except Exception as exc:
                raise RuntimeError("uninspectable HTTP route; refusing startup") from exc
            if not isinstance(nested, list):
                raise RuntimeError("uninspectable HTTP route; refusing startup")
            pending.extend(nested)
            continue
        children = getattr(route, "routes", None)
        if isinstance(children, list):
            prefix = path if isinstance(path, str) else ""
            for child in children:
                child_path = getattr(child, "path", None)
                if (
                    prefix
                    and isinstance(child_path, str)
                    and not child_path.startswith(prefix.rstrip("/") + "/")
                    and child_path != prefix
                ):
                    joined = prefix.rstrip("/") + "/" + child_path.lstrip("/")
                    _reject_secret_path(joined)
            pending.extend(children)
            continue
        if not isinstance(path, str):
            raise RuntimeError("uninspectable HTTP route; refusing startup")


def _reject_secret_path(path: str) -> None:
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
