"""Canonical Zaibatsu gate for the Python spine.

The standalone C# gate and the Python backend converged on the same boundary
concerns (request identity, access logging, and bounded rate limiting).  Keep a
single Python implementation by making this module the Zaibatsu-facing facade
for the already-hardened ``api_middleware`` stack instead of maintaining a
second, subtly different middleware chain.

Starlette applies middleware in LIFO order; ``install_middleware`` deliberately
preserves ``api_middleware.install_middleware`` ordering and behavior.
"""
from __future__ import annotations

from api_middleware import (
    AccessLogMiddleware,
    RateLimiterMiddleware,
    RequestIdMiddleware,
    RoutePrivacyMiddleware,
    get_stats as _get_stats,
    install_middleware as _install_api_middleware,
)


def install_middleware(app) -> None:
    """Install the canonical request gate on a FastAPI/Starlette application."""
    _install_api_middleware(app)


def get_stats() -> dict:
    """Return the gate's bounded in-process telemetry snapshot."""
    return _get_stats()


__all__ = [
    "AccessLogMiddleware",
    "RateLimiterMiddleware",
    "RequestIdMiddleware",
    "RoutePrivacyMiddleware",
    "get_stats",
    "install_middleware",
]
