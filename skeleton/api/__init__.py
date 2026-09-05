"""REST API surface — routes, bootstrap, middleware, auth, caching, filters."""

from .auth import AuthContext, role_dependency, scope_dependency
from .cache_control import CachePolicy, CacheProfile, etag_for, headers_for
from .deprecations import Deprecation, DeprecationRegistry
from .errors import ApiErrorResponse, map_error
from .filters import Filter, FilterOperation, FilterParser
from .idempotency import IdempotencyError, IdempotencyKey, IdempotencyStore, parse_key
from .middleware import (
    AuthError,
    BearerAuth,
    MiddlewareError,
    RateLimiter,
    RateLimitError,
    get_request_id,
)
from .routes import router
from .server import AppState, create_app, get_state, lifespan
from .telemetry import RouteMetrics, RouteTelemetry
from .validation import FieldRule, RequestValidator, ValidationIssue, ValidationError
from .versioning import SUPPORTED, Version, VersionError, extract, negotiate
from .webhooks import Subscription, WebhookDispatcher, WebhookError

__all__ = [
    "AuthContext",
    "role_dependency",
    "scope_dependency",
    "CachePolicy",
    "CacheProfile",
    "etag_for",
    "headers_for",
    "Deprecation",
    "DeprecationRegistry",
    "ApiErrorResponse",
    "map_error",
    "Filter",
    "FilterOperation",
    "FilterParser",
    "IdempotencyError",
    "IdempotencyKey",
    "IdempotencyStore",
    "parse_key",
    "AuthError",
    "BearerAuth",
    "MiddlewareError",
    "RateLimiter",
    "RateLimitError",
    "get_request_id",
    "router",
    "AppState",
    "create_app",
    "get_state",
    "lifespan",
    "RouteMetrics",
    "RouteTelemetry",
    "FieldRule",
    "RequestValidator",
    "ValidationIssue",
    "ValidationError",
    "SUPPORTED",
    "Version",
    "VersionError",
    "extract",
    "negotiate",
    "Subscription",
    "WebhookDispatcher",
    "WebhookError",
]
