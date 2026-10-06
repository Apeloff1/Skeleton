"""Typed contracts for deterministic reverse-engineering evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


class ReverseEngineeringError(ValueError):
    """Raised when research evidence violates the governed contract."""


class ProbeKind(str, Enum):
    DETERMINISM = "determinism"
    CONTEXT = "context"
    STATE = "state"
    FORMAT = "format"
    REFUSAL = "refusal"
    TOOLING = "tooling"
    REASONING = "reasoning"
    CUSTOM = "custom"


def canonical_json(value: Any) -> str:
    """Encode JSON-compatible values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorizationScope:
    """Explicit scope for a reverse-engineering session.

    A session may probe only targets named here. Artifact extraction additionally
    requires artifact_inspection=True and is expected to pass ProvenanceGate.
    """

    target_ids: tuple[str, ...]
    purpose: str
    artifact_inspection: bool = False
    allow_external_targets: bool = False

    def __post_init__(self) -> None:
        cleaned = tuple(sorted({item.strip() for item in self.target_ids if item.strip()}))
        if not cleaned:
            raise ReverseEngineeringError("authorization scope requires at least one target")
        if not self.purpose.strip():
            raise ReverseEngineeringError("authorization scope requires a purpose")
        object.__setattr__(self, "target_ids", cleaned)

    def authorizes(self, target_id: str) -> bool:
        return target_id in self.target_ids


@dataclass(frozen=True)
class ProbeCase:
    """A single black-box probe.

    payload is deliberately ephemeral. Persistent evidence stores only its
    digest and non-sensitive labels unless a caller separately owns and records
    the source data under a governed provenance path.
    """

    probe_id: str
    kind: ProbeKind
    payload: Any
    tags: tuple[str, ...] = ()
    expected_repeatability: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.probe_id.strip():
            raise ReverseEngineeringError("probe_id must be non-empty")
        object.__setattr__(self, "tags", tuple(sorted(set(self.tags))))

    @property
    def payload_digest(self) -> str:
        return stable_digest(self.payload)


@dataclass(frozen=True)
class Observation:
    target_id: str
    probe_id: str
    kind: ProbeKind
    input_digest: str
    output_digest: str
    output_shape: str
    success: bool
    error_type: str | None = None
    feature_flags: tuple[str, ...] = ()
    ordinal: int = 0

    def __post_init__(self) -> None:
        if not self.target_id or not self.probe_id:
            raise ReverseEngineeringError("observation identity must be non-empty")
        if len(self.input_digest) != 64 or len(self.output_digest) != 64:
            raise ReverseEngineeringError("observation digests must be sha256 hex digests")
        object.__setattr__(self, "feature_flags", tuple(sorted(set(self.feature_flags))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "probe_id": self.probe_id,
            "kind": self.kind.value,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "output_shape": self.output_shape,
            "success": self.success,
            "error_type": self.error_type,
            "feature_flags": list(self.feature_flags),
            "ordinal": self.ordinal,
        }


@dataclass(frozen=True)
class InferenceClaim:
    claim_id: str
    statement: str
    confidence: float
    evidence_probe_ids: tuple[str, ...]
    falsifiers: tuple[str, ...] = ()
    status: str = "hypothesis"

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.statement.strip():
            raise ReverseEngineeringError("inference claim identity and statement are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ReverseEngineeringError("confidence must be within [0, 1]")
        if not self.evidence_probe_ids:
            raise ReverseEngineeringError("inference claim requires supporting evidence")
        if self.status not in {"hypothesis", "supported", "rejected"}:
            raise ReverseEngineeringError("invalid inference status")
        object.__setattr__(self, "evidence_probe_ids", tuple(sorted(set(self.evidence_probe_ids))))
        object.__setattr__(self, "falsifiers", tuple(sorted(set(self.falsifiers))))

    @property
    def promotable(self) -> bool:
        return self.status == "supported" and self.confidence >= 0.8


@dataclass(frozen=True)
class EvidenceBundle:
    target_id: str
    observations: tuple[Observation, ...]
    protocol_version: str = "ai.reverse-engineering.evidence.v1"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.target_id:
            raise ReverseEngineeringError("evidence target_id must be non-empty")
        if any(obs.target_id != self.target_id for obs in self.observations):
            raise ReverseEngineeringError("evidence bundle cannot mix targets")
        ordered = tuple(sorted(self.observations, key=lambda o: (o.probe_id, o.ordinal)))
        object.__setattr__(self, "observations", ordered)
        object.__setattr__(self, "notes", tuple(self.notes))

    @property
    def digest(self) -> str:
        return stable_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "target_id": self.target_id,
            "observations": [obs.as_dict() for obs in self.observations],
            "notes": list(self.notes),
        }

    def probe_ids(self) -> tuple[str, ...]:
        return tuple(sorted({obs.probe_id for obs in self.observations}))


def ensure_supported_claims(
    claims: Sequence[InferenceClaim],
    bundle: EvidenceBundle,
) -> None:
    """Fail closed if a supported claim references evidence that is not present."""
    available = set(bundle.probe_ids())
    for claim in claims:
        if claim.status != "supported":
            continue
        missing = set(claim.evidence_probe_ids) - available
        if missing:
            raise ReverseEngineeringError(
                f"supported claim {claim.claim_id!r} references missing probes: {sorted(missing)!r}"
            )
