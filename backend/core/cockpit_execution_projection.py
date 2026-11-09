"""Read-only cockpit projection for governed execution lifecycle evidence.

The cockpit needs operator-visible execution state without direct access to
pending-operation payloads, receipts, audit details, credentials, or mutation
capabilities. This module projects verified :class:`LifecycleEvidence` into a
small bounded status contract suitable for UI synchronization.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from core.execution_evidence import LifecycleEvidence, verify_evidence_digest

_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LENGTH = 128
_MAX_ANOMALIES = 16
_ALLOWED_CONFIDENCE = frozenset({"low", "medium", "high"})


@dataclass(frozen=True, slots=True)
class CockpitExecutionProjection:
    operation_id: str
    state: str
    confidence: str
    pending: bool
    executor_bound: bool
    receipt_present: bool
    anomaly_count: int
    anomalies: tuple[str, ...]
    evidence_sha256: str
    writable: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "operationId": self.operation_id,
            "state": self.state,
            "confidence": self.confidence,
            "pending": self.pending,
            "executorBound": self.executor_bound,
            "receiptPresent": self.receipt_present,
            "anomalyCount": self.anomaly_count,
            "anomalies": list(self.anomalies),
            "evidenceSha256": self.evidence_sha256,
            "writable": self.writable,
        }


def _bounded_identifier(value: str, field: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _MAX_ID_LENGTH
        or not _ID_PATTERN.fullmatch(normalized)
    ):
        raise ValueError(f"{field} must be a bounded canonical identifier")
    return normalized


def project_execution_evidence(
    evidence: LifecycleEvidence,
    *,
    require_verified_digest: bool = True,
) -> CockpitExecutionProjection:
    """Project durable lifecycle evidence without exposing execution payloads."""

    if not isinstance(evidence, LifecycleEvidence):
        raise TypeError("evidence must be LifecycleEvidence")
    if require_verified_digest and not verify_evidence_digest(evidence):
        raise ValueError("execution evidence digest verification failed")
    if evidence.confidence not in _ALLOWED_CONFIDENCE:
        raise ValueError("unsupported execution confidence")
    if not _SHA256_PATTERN.fullmatch(evidence.evidence_sha256):
        raise ValueError("execution evidence digest must be sha256 hex")

    anomalies = tuple(
        _bounded_identifier(value, "anomaly")
        for value in evidence.anomalies[:_MAX_ANOMALIES]
    )
    return CockpitExecutionProjection(
        operation_id=_bounded_identifier(evidence.operation_id, "operation_id"),
        state=_bounded_identifier(evidence.state, "state"),
        confidence=evidence.confidence,
        pending=evidence.pending,
        executor_bound=evidence.executor_bound,
        receipt_present=evidence.receipt_present,
        anomaly_count=len(evidence.anomalies),
        anomalies=anomalies,
        evidence_sha256=evidence.evidence_sha256,
    )
