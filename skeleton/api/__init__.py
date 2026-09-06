"""REST API surface — HMAC seal, idempotency, Gate middleware."""

from skeleton.api.hmac_seal import mint_seal, require_seal, verify_seal
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.middleware import (
    AuthError,
    AuthMiddleware,
    BearerAuth,
    BodyBoundMiddleware,
    GatePolicy,
    MiddlewareError,
    PolicyGateMiddleware,
    RateLimitError,
    RateLimiter,
    RequestSealMiddleware,
    WormAuditMiddleware,
    get_request_id,
    install_gate,
)

__all__ = [
    "mint_seal",
    "require_seal",
    "verify_seal",
    "IdempotencyGuard",
    "AuthError",
    "AuthMiddleware",
    "BearerAuth",
    "BodyBoundMiddleware",
    "GatePolicy",
    "MiddlewareError",
    "PolicyGateMiddleware",
    "RateLimitError",
    "RateLimiter",
    "RequestSealMiddleware",
    "WormAuditMiddleware",
    "get_request_id",
    "install_gate",
]
