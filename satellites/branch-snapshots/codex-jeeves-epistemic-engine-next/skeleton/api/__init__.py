"""REST API surface — HMAC seal, idempotency, Gate middleware."""

from skeleton.api.hmac_seal import HMACSeal, mint_seal, require_seal, verify_seal
from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.admit_write import (
    WriteAdmitMiddleware,
    admit_write,
    set_defaults as set_admit_write_defaults,
)
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
    "HMACSeal",
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
    "WriteAdmitMiddleware",
    "admit_write",
    "set_admit_write_defaults",
    "get_request_id",
    "install_gate",
]
