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
    if routes is None:
        raise RuntimeError("HTTP route inventory unavailable; refusing startup")
    for route in routes:
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            raise RuntimeError("uninspectable HTTP route; refusing startup")
        # Starlette provides decoded ASGI paths; also inspect percent-encoded
        # aliases so registration spelling cannot bypass the source guard.
        decoded = unquote(path).replace("//", "/").casefold()
        if decoded == "/api/v1/secrets" or decoded.startswith("/api/v1/secrets/"):
            raise RuntimeError(
                "unchartered cortex secrets HTTP route is forbidden: "
                "keep cortex_routes unmounted"
            )


__all__ = ["reject_cortex_secret_routes"]
