"""Secrets vault subsystem — sealing, rotation, audit, access, KMS, store, keys, quorum, recovery."""

from .shamir import SealingError, ShamirSeal, Share
from .rotation import RotationPolicy, RotationScheduler, RotationTrigger
from .audit import AuditEntry, AuditLog
from .access import AccessDenied, AccessPolicy, Role
from .kms import DataKey, EnvelopeError, EnvelopeKMS
from .store import IntegrityError, SealedStore
from .keys import KeyRegistry, KeyVersion, KeyVersionError
from .quorum import QuorumError, QuorumGate, QuorumRequest
from .recovery import RecoveryError, RecoveryManager, RecoverySnapshot

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
    "KeyRegistry",
    "KeyVersion",
    "KeyVersionError",
    "QuorumError",
    "QuorumGate",
    "QuorumRequest",
    "RecoveryError",
    "RecoveryManager",
    "RecoverySnapshot",
]
