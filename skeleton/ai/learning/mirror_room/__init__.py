"""Bounded offline Mirror Room learning core.

This package intentionally exports only the hermetic learning/evaluation path.
Adversarial campaigns, UI/observability, archives, and production deployment
remain separate authorities.
"""

from .contracts import (
    EpisodeOutcome,
    HardExample,
    LearningFeedback,
    MirrorBudget,
    MirrorCandidate,
    MirrorMetricPolicy,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    SandboxPolicy,
    ScenarioSplit,
)
from .curriculum import (
    CurriculumItem,
    CurriculumPlan,
    CurriculumPolicy,
    build_curriculum,
)
from .engine import (
    CandidateEvaluation,
    CandidateGenerator,
    GenerationRecord,
    MirrorRoom,
    MirrorRunReceipt,
)
from .evaluation import (
    ComparisonReport,
    MetricComparison,
    PairedEvaluator,
    ScenarioComparison,
)
from .integrity import (
    CrossSplitSimilarity,
    SplitIntegrityPolicy,
    SplitIntegrityReport,
    inspect_split_integrity,
    validate_split_integrity,
)
from .promotion import (
    MirrorPromotionEvidence,
    qualify_for_external_promotion,
)
from .sandbox import (
    EpisodeReceipt,
    MirrorSandbox,
    SandboxExecutor,
    SandboxUsage,
)

__all__ = [
    "CandidateEvaluation",
    "CandidateGenerator",
    "ComparisonReport",
    "CrossSplitSimilarity",
    "CurriculumItem",
    "CurriculumPlan",
    "CurriculumPolicy",
    "EpisodeOutcome",
    "EpisodeReceipt",
    "GenerationRecord",
    "HardExample",
    "LearningFeedback",
    "MetricComparison",
    "MirrorBudget",
    "MirrorCandidate",
    "MirrorMetricPolicy",
    "MirrorPromotionEvidence",
    "MirrorRoom",
    "MirrorRoomError",
    "MirrorRoomSpec",
    "MirrorRunReceipt",
    "MirrorSandbox",
    "MirrorScenario",
    "PairedEvaluator",
    "SandboxExecutor",
    "SandboxPolicy",
    "SandboxUsage",
    "ScenarioComparison",
    "ScenarioSplit",
    "SplitIntegrityPolicy",
    "SplitIntegrityReport",
    "build_curriculum",
    "inspect_split_integrity",
    "qualify_for_external_promotion",
    "validate_split_integrity",
]
