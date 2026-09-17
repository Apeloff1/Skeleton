"""Scientific governance primitives for Jeeves.

The science package keeps architectural evolution evidence-bearing.  Newer is
not treated as better by default: candidate mechanisms must preserve mandatory
invariants and earn promotion against explicit criteria.
"""

from .lineage import (
    ArchitecturalLineage,
    EvidenceGrade,
    LineageDomain,
    PromotionCriterion,
    PromotionDecision,
    PromotionStatus,
    TheoryRecord,
    default_lineage,
)

__all__ = [
    "ArchitecturalLineage",
    "EvidenceGrade",
    "LineageDomain",
    "PromotionCriterion",
    "PromotionDecision",
    "PromotionStatus",
    "TheoryRecord",
    "default_lineage",
]
