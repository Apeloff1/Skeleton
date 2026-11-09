"""Assurance evidence ingestion for canonical execution results.

Keeps evidence handling bounded and deterministic before memory updates.
"""

from dataclasses import dataclass
from enum import Enum
from .canonical import CanonicalEnvelope, evidence_ref_identity


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

    if not envelope.evidence or any(
        not item.source or not item.digest or not item.category
        for item in envelope.evidence
    ):
        return EvidenceDecision(
            EvidenceDisposition.TEMPORARY,
            "missing evidence references",
            (),
        )

    evidence_ids = tuple(
        sorted(
            {
                evidence_ref_identity(item)
                for item in envelope.evidence
            }
        )
    )

    return EvidenceDecision(
        EvidenceDisposition.STABLE,
        "validated execution evidence",
        evidence_ids,
    )
