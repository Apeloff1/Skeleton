"""
Skeleton API Package — Additional utilities

Exports:
- HMACSeal: Request signing
- require_seal: FastAPI dependency
- IdempotencyGuard: Deduplication
"""

from skeleton.api.hmac_seal import HMACSeal, require_seal
from skeleton.api.idempotency import IdempotencyGuard

__all__ = ["HMACSeal", "require_seal", "IdempotencyGuard"]
