from dataclasses import dataclass
from enum import Enum
from typing import Any


class MemoryClass(str, Enum):
    STABLE = "stable"
    TEMPORARY = "temporary"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MemoryDecision:
    classification: MemoryClass
    reason: str
    evidence_digest: str | None = None


def classify_evidence(
    *,
    evidence_digest: str | None,
    verified: bool,
    regression_passed: bool,
    source_kind: str,
) -> MemoryDecision:
    """Classify knowledge before it can enter durable memory.

    Durable state requires verified evidence and successful regression
    validation. Everything else remains temporary or is rejected.
    """
    if not evidence_digest:
        return MemoryDecision(
            MemoryClass.REJECTED,
            "missing_evidence_digest",
        )

    if not verified:
        return MemoryDecision(
            MemoryClass.TEMPORARY,
            "awaiting_verification",
            evidence_digest,
        )

    if not regression_passed:
        return MemoryDecision(
            MemoryClass.TEMPORARY,
            "regression_not_passed",
            evidence_digest,
        )

    if source_kind not in {
        "worker_result",
        "contract_validation",
        "workflow_validation",
    }:
        return MemoryDecision(
            MemoryClass.REJECTED,
            "unsupported_memory_source",
            evidence_digest,
        )

    return MemoryDecision(
        MemoryClass.STABLE,
        "validated_evidence",
        evidence_digest,
    )
