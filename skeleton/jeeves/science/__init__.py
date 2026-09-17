"""Scientific governance primitives for Jeeves.

The science package keeps architectural evolution evidence-bearing.  Newer is
not treated as better by default: candidate mechanisms must preserve mandatory
invariants and earn promotion against explicit criteria.
"""

from .corpus import (
    ArtifactKind,
    ClaimEdge,
    ClaimRelation,
    ClaimStatus,
    EvidenceKind,
    EvidenceProfile,
    EvidenceSnapshot,
    FrontierEntry,
    ResearchArtifact,
    ScientificClaim,
    ScientificEvidenceLedger,
)
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
    "ArtifactKind",
    "ClaimEdge",
    "ClaimRelation",
    "ClaimStatus",
    "EvidenceGrade",
    "EvidenceKind",
    "EvidenceProfile",
    "EvidenceSnapshot",
    "FrontierEntry",
    "LineageDomain",
    "PromotionCriterion",
    "PromotionDecision",
    "PromotionStatus",
    "ResearchArtifact",
    "ScientificClaim",
    "ScientificEvidenceLedger",
    "TheoryRecord",
    "default_lineage",
]
