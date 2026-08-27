"""REST API surface — routers, server, middleware, auth, versioning, webhooks, idempotency, validation, deprecations."""

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
from .idempotency import IdempotencyError, IdempotencyKey, IdempotencyStore, parse_key
from .validation import FieldRule, RequestValidator, ValidationIssue, ValidationError
from .deprecations import Deprecation, DeprecationRegistry

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
    "IdempotencyError",
    "IdempotencyKey",
    "IdempotencyStore",
    "parse_key",
    "FieldRule",
    "RequestValidator",
    "ValidationIssue",
    "ValidationError",
    "Deprecation",
    "DeprecationRegistry",
]
