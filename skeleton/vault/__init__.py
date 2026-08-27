"""Secrets vault subsystem — sealing, threshold, rotation, audit, access."""

from .shamir import SealingError, ShamirSeal, Share
from .rotation import RotationPolicy, RotationScheduler, RotationTrigger
from .audit import AuditEntry, AuditLog
from .access import AccessDenied, AccessPolicy, Role

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
]
