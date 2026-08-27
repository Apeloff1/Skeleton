"""Secrets vault subsystem — sealing, threshold, rotation, audit, access, KMS, sealed store."""

from .shamir import SealingError, ShamirSeal, Share
from .rotation import RotationPolicy, RotationScheduler, RotationTrigger
from .audit import AuditEntry, AuditLog
from .access import AccessDenied, AccessPolicy, Role
from .kms import DataKey, EnvelopeError, EnvelopeKMS
from .store import IntegrityError, SealedStore

__all__ = [
    "Share",
    "ShamirSeal",
    "SealingError",
    "RotationPolicy",
    "RotationScheduler",
    "RotationTrigger",
    "AuditEntry",
    "AuditLog",
    "AccessDenied",
    "AccessPolicy",
    "Role",
    "DataKey",
    "EnvelopeError",
    "EnvelopeKMS",
    "IntegrityError",
    "SealedStore",
]
