"""Typed error lattice for Skeleton — extended v16.1.

Every error raised inside Skeleton derives from :class:`SkeletonError` and
carries a stable machine-readable ``code``, a ``severity``, and a structured
``context`` dict safe to serialise into logs and API responses. Subsystems
extend the lattice with their own families; the API boundary maps each family
onto HTTP statuses deterministically via :func:`http_status_for`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SkeletonError(Exception):
    """Root of the lattice."""

    code: str = "SKL.UNKNOWN"
    severity: Severity = Severity.ERROR
    http_status: int = 500

    def __init__(self, message: str, *, code: Optional[str] = None,
                 severity: Optional[Severity] = None,
                 context: Optional[Dict[str, Any]] = None,
                 cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if severity is not None:
            self.severity = severity
        self.context: Dict[str, Any] = dict(context or {})
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": type(self).__name__,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "context": self.context,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Kernel family
# ---------------------------------------------------------------------------

class KernelError(SkeletonError):
    code = "KRN.UNKNOWN"


class RegistryError(KernelError):
    code = "KRN.REGISTRY"
    http_status = 409


class EventBusError(KernelError):
    code = "KRN.EVENT_BUS"


class IdentityError(KernelError):
    code = "KRN.IDENTITY"
    http_status = 400


class ConfigurationError(KernelError):
    code = "KRN.CONFIG"
    severity = Severity.CRITICAL


# ---------------------------------------------------------------------------
# Agent family
# ---------------------------------------------------------------------------

class AgentError(SkeletonError):
    code = "AGT.UNKNOWN"


class ConsensusError(AgentError):
    code = "AGT.CONSENSUS"
    http_status = 409


class SchedulingError(AgentError):
    code = "AGT.SCHEDULING"
    http_status = 503


class AgentUnavailable(AgentError):
    code = "AGT.UNAVAILABLE"
    http_status = 503


# ---------------------------------------------------------------------------
# Pipeline family
# ---------------------------------------------------------------------------

class PipelineError(SkeletonError):
    code = "PPL.UNKNOWN"


class GenerationError(PipelineError):
    code = "PPL.GENERATION"
    http_status = 502


class ValidationError(PipelineError):
    code = "PPL.VALIDATION"
    severity = Severity.WARNING
    http_status = 422


class StageError(PipelineError):
    code = "PPL.STAGE"


# ---------------------------------------------------------------------------
# Jeeves family
# ---------------------------------------------------------------------------

class JeevesError(SkeletonError):
    code = "JEE.UNKNOWN"


class SessionError(JeevesError):
    code = "JEE.SESSION"
    http_status = 409


# ---------------------------------------------------------------------------
# Retrieval family (quad lattice)
# ---------------------------------------------------------------------------

class RetrievalError(SkeletonError):
    code = "RET.UNKNOWN"


class FusionError(RetrievalError):
    code = "RET.FUSION"


# ---------------------------------------------------------------------------
# Forge family
# ---------------------------------------------------------------------------

class ForgeError(SkeletonError):
    code = "FRG.UNKNOWN"


class BlueprintError(ForgeError):
    code = "FRG.BLUEPRINT"
    http_status = 422


class MaterialisationError(ForgeError):
    code = "FRG.MATERIALISE"


# ---------------------------------------------------------------------------
# Vault family (secrets)
# ---------------------------------------------------------------------------

class VaultError(SkeletonError):
    code = "VLT.UNKNOWN"
    severity = Severity.CRITICAL


class SecretNotFound(VaultError):
    code = "VLT.NOT_FOUND"
    severity = Severity.WARNING
    http_status = 404


class AccessDenied(VaultError):
    code = "VLT.ACCESS_DENIED"
    severity = Severity.WARNING
    http_status = 403


class RotationError(VaultError):
    code = "VLT.ROTATION"


class SealedVaultError(VaultError):
    code = "VLT.SEALED"
    http_status = 423


# ---------------------------------------------------------------------------
# HTTP mapping
# ---------------------------------------------------------------------------

def http_status_for(exc: SkeletonError) -> int:
    """Deterministic error→HTTP mapping used by the API boundary."""
    return getattr(exc, "http_status", 500)
