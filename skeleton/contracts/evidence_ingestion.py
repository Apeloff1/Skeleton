"""Assurance evidence ingestion for canonical execution results.

Keeps evidence handling bounded and deterministic before memory updates.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .canonical import CanonicalEnvelope


class EvidenceDisposition(str, Enum):
    STABLE = "stable"
    TEMPORARY = "temporary"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EvidenceDecision:
    disposition: EvidenceDisposition
    reason: str
    evidence_ids: tuple[str, ...]


def ingest_execution_evidence(
    envelope: CanonicalEnvelope,
    *,
    required_kind: str = "execution_result",
) -> EvidenceDecision:
    """Classify evidence attached to a validated worker result.

    Durable memory is only allowed from complete execution results with
    attached evidence references. Incomplete observations remain temporary.
    """

    if envelope.kind != required_kind:
        return EvidenceDecision(
            EvidenceDisposition.REJECTED,
            "unexpected envelope kind",
            (),
        )

    evidence_ids = tuple(
        getattr(item, "evidence_id", "")
        for item in envelope.evidence
    )

    if not evidence_ids or any(not item for item in evidence_ids):
        return EvidenceDecision(
            EvidenceDisposition.TEMPORARY,
            "missing evidence references",
            evidence_ids,
        )

    return EvidenceDecision(
        EvidenceDisposition.STABLE,
        "validated execution evidence",
        evidence_ids,
    )
