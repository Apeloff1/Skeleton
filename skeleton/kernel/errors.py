"""The typed error lattice for Skeleton.

Every failure raised inside the platform derives from :class:`SkeletonError`.
Each error carries three machine-readable facets:

- ``code`` — stable, namespaced string (``AGENT.CONSENSUS.FAILED``) safe for
  clients, alerts, and log aggregation to key on. Codes never change without
  a major version bump.
- ``severity`` — drives alerting and log level mapping.
- ``context`` — structured payload, guaranteed JSON-serialisable, carrying
  whatever the raise site knew (ids, ballot records, validation failures).

The lattice mirrors the subsystem tree so a caller can catch at any altitude:
catch ``PipelineError`` to handle any pipeline failure, or
``BalanceSimulationError`` for one specific stage.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Error severity, ordered. Used for alert routing and log levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "warning": 1, "error": 2, "critical": 3}[self.value]

    def at_least(self, other: "Severity") -> bool:
        return self.rank >= other.rank


class SkeletonError(Exception):
    """Root of every error Skeleton raises.

    Parameters
    ----------
    message:
        Human-readable description. Rendered into logs and (for 4xx-class
        errors) into API responses.
    code:
        Machine-readable, namespaced, stable. Defaults to the class's
        ``default_code``.
    severity:
        Alert routing severity; defaults to ``Severity.ERROR``.
    context:
        Structured payload. Must be JSON-serialisable; the constructor
        coerces non-serialisable values to ``repr`` rather than failing.
    """

    default_code: str = "SKELETON.ERROR"
    default_severity: Severity = Severity.ERROR
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        severity: Severity | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.severity = severity or self.default_severity
        self.context = self._sanitise_context(context or {})

    @staticmethod
    def _sanitise_context(context: dict[str, Any]) -> dict[str, Any]:
        """Guarantee the context payload is JSON-serialisable."""
        import json

        safe: dict[str, Any] = {}
        for key, value in context.items():
            try:
                json.dumps(value)
                safe[str(key)] = value
            except (TypeError, ValueError):
                safe[str(key)] = repr(value)
        return safe

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API responses and structured logs."""
        return {
            "error": type(self).__name__,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "context": self.context,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Kernel
# ---------------------------------------------------------------------------

class KernelError(SkeletonError):
    default_code = "KERNEL.ERROR"


class RegistryError(KernelError):
    default_code = "KERNEL.REGISTRY.ERROR"
    http_status = 409


class DuplicateCapabilityError(RegistryError):
    default_code = "KERNEL.REGISTRY.DUPLICATE"


class CapabilityNotFoundError(RegistryError):
    default_code = "KERNEL.REGISTRY.NOT_FOUND"
    http_status = 404


class EventBusError(KernelError):
    default_code = "KERNEL.EVENTS.ERROR"


class InvalidIdentifierError(KernelError):
    default_code = "KERNEL.ID.INVALID"
    http_status = 400


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentError(SkeletonError):
    default_code = "AGENT.ERROR"


class AgentNotFoundError(AgentError):
    default_code = "AGENT.NOT_FOUND"
    http_status = 404


class NoCapableAgentError(AgentError):
    default_code = "AGENT.ROUTE.NO_CAPABLE"
    http_status = 503


class ConsensusError(AgentError):
    default_code = "AGENT.CONSENSUS.FAILED"
    severity = Severity.WARNING
    http_status = 409


class SchedulingError(AgentError):
    default_code = "AGENT.SCHEDULE.ERROR"


class TaskDeadLetteredError(SchedulingError):
    default_code = "AGENT.SCHEDULE.DEAD_LETTER"
    severity = Severity.WARNING


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------

class PipelineError(SkeletonError):
    default_code = "PIPELINE.ERROR"


class PipelineValidationError(PipelineError):
    default_code = "PIPELINE.VALIDATION"
    severity = Severity.WARNING
    http_status = 422


class GenerationError(PipelineError):
    default_code = "PIPELINE.GENERATION"


class BalanceSimulationError(PipelineError):
    default_code = "PIPELINE.BALANCE_SIM"


class PipelineTimeoutError(PipelineError):
    default_code = "PIPELINE.TIMEOUT"
    http_status = 504


# ---------------------------------------------------------------------------
# Jeeves
# ---------------------------------------------------------------------------

class JeevesError(SkeletonError):
    default_code = "JEE.ERROR"


class SessionNotFoundError(JeevesError):
    default_code = "JEE.SESSION.NOT_FOUND"
    http_status = 404


class RagUnavailableError(JeevesError):
    default_code = "JEE.RAG.UNAVAILABLE"
    severity = Severity.WARNING
    http_status = 503


class MatrixError(JeevesError):
    default_code = "JEE.MATRIX.ERROR"


# ---------------------------------------------------------------------------
# Forge
# ---------------------------------------------------------------------------

class ForgeError(SkeletonError):
    default_code = "FORGE.ERROR"


class BlueprintValidationError(ForgeError):
    default_code = "FORGE.BLUEPRINT.VALIDATION"
    severity = Severity.WARNING
    http_status = 422


class DependencyCycleError(ForgeError):
    default_code = "FORGE.BLUEPRINT.CYCLE"
    severity = Severity.WARNING
    http_status = 422


class MaterialisationError(ForgeError):
    default_code = "FORGE.MATERIALISATION"


# ---------------------------------------------------------------------------
# HTTP mapping
# ---------------------------------------------------------------------------

def http_status_for(error: SkeletonError) -> int:
    """Deterministically map any SkeletonError onto an HTTP status code."""
    return error.http_status
