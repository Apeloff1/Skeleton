"""REST API surface — FastAPI routers, server bootstrap, middleware."""

from .routes import router
from .server import AppState, bootstrap, get_state, lifespan
from .middleware import (
    AuthError,
    BearerAuth,
    MiddlewareError,
    RateLimiter,
    RateLimitError,
    get_request_id,
)

__all__ = [
    "router",
    "AppState",
    "bootstrap",
    "get_state",
    "lifespan",
    "AuthError",
    "BearerAuth",
    "MiddlewareError",
    "RateLimiter",
    "RateLimitError",
    "get_request_id",
]
