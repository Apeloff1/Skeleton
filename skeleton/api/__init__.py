"""REST API surface — FastAPI routers, server bootstrap, middleware, auth."""

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
from .auth import AuthContext, role_dependency, scope_dependency
from .versioning import SUPPORTED, Version, VersionError, extract, negotiate
from .webhooks import Subscription, WebhookDispatcher, WebhookError

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
    "AuthContext",
    "role_dependency",
    "scope_dependency",
    "SUPPORTED",
    "Version",
    "VersionError",
    "extract",
    "negotiate",
    "Subscription",
    "WebhookDispatcher",
    "WebhookError",
]
