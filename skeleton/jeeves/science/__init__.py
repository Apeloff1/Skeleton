"""Scientific governance primitives for Jeeves.

The science package keeps architectural evolution evidence-bearing. Newer is
not treated as better by default: candidate mechanisms must preserve mandatory
invariants and earn promotion against explicit criteria. Chronological replay
also prevents hindsight by enforcing historical availability and data custody.
"""

from .chronological_frontier import (
    ChallengerComparison,
    ChronologicalFrontierTournament,
    ChronologicalReplayReport,
    ForecastFamily,
    ForecastTechnique,
    FrontierDecisionStatus,
    FrontierTournamentPolicy,
    HistoricalEvaluation,
    MetricComparison,
    MetricDirection,
    MetricRule,
    TechniqueRegistry,
    YearFrontierDecision,
    default_metric_rules,
    default_prediction_lineage,
)
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
    "ChallengerComparison",
    "ChronologicalFrontierTournament",
    "ChronologicalReplayReport",
    "ClaimEdge",
    "ClaimRelation",
    "ClaimStatus",
    "EvidenceGrade",
    "EvidenceKind",
    "EvidenceProfile",
    "EvidenceSnapshot",
    "ForecastFamily",
    "ForecastTechnique",
    "FrontierDecisionStatus",
    "FrontierEntry",
    "FrontierTournamentPolicy",
    "HistoricalEvaluation",
    "LineageDomain",
    "MetricComparison",
    "MetricDirection",
    "MetricRule",
    "PromotionCriterion",
    "PromotionDecision",
    "PromotionStatus",
    "ResearchArtifact",
    "ScientificClaim",
    "ScientificEvidenceLedger",
    "TechniqueRegistry",
    "TheoryRecord",
    "YearFrontierDecision",
    "default_lineage",
    "default_metric_rules",
    "default_prediction_lineage",
]
