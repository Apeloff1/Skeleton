"""Secrets vault subsystem — sealed store, policies, recovery, entropy, KMS, quorum."""

from .access import AccessDenied, AccessPolicy, Role
from .audit import AuditEntry, AuditLog
from .entropy import EntropyError, EntropyQuality, EntropyRegistry, EntropySource
from .kms import DataKey, EnvelopeError, EnvelopeKMS
from .keys import KeyRegistry, KeyVersion, KeyVersionError
from .policies import PolicyRegistry, PolicyViolation, VaultPolicy, enforce_plaintext_minimum, require_prefix
from .quorum import QuorumError, QuorumGate, QuorumRequest
from .recovery import RecoveryError, RecoveryManager, RecoverySnapshot
from .rotation import RotationPolicy, RotationScheduler, RotationTrigger
from .shamir import SealingError, ShamirSeal, Share
from .store import IntegrityError, SealedStore

__all__ = [
    "AccessDenied",
    "AccessPolicy",
    "Role",
    "AuditEntry",
    "AuditLog",
    "EntropyError",
    "EntropyQuality",
    "EntropyRegistry",
    "EntropySource",
    "DataKey",
    "EnvelopeError",
    "EnvelopeKMS",
    "KeyRegistry",
    "KeyVersion",
    "KeyVersionError",
    "PolicyRegistry",
    "PolicyViolation",
    "VaultPolicy",
    "enforce_plaintext_minimum",
    "require_prefix",
    "QuorumError",
    "QuorumGate",
    "QuorumRequest",
    "RecoveryError",
    "RecoveryManager",
    "RecoverySnapshot",
    "RotationPolicy",
    "RotationScheduler",
    "RotationTrigger",
    "SealingError",
    "ShamirSeal",
    "Share",
    "IntegrityError",
    "SealedStore",
]
