"""Research evidence and historical lineage; this namespace grants no production authority."""

from .source_lineage import (
    CitationEdge,
    CitationGraphReport,
    CitationRelation,
    CitationSpec,
    HistoricalTechnique,
    IngestionReceipt,
    ReplicationOutcome,
    ReplicationRecord,
    ResearchClaim,
    ResearchLineageError,
    ResearchSource,
    ResearchSourceRegistry,
    RetractionRecord,
    SourceStatus,
    content_digest,
)

__all__ = [
    "CitationEdge",
    "CitationGraphReport",
    "CitationRelation",
    "CitationSpec",
    "HistoricalTechnique",
    "IngestionReceipt",
    "ReplicationOutcome",
    "ReplicationRecord",
    "ResearchClaim",
    "ResearchLineageError",
    "ResearchSource",
    "ResearchSourceRegistry",
    "RetractionRecord",
    "SourceStatus",
    "content_digest",
    "EvidenceGraph",
    "EvidenceNode",
    "ExperimentPlan",
    "Outcome",
    "ReproductionRecord",
    "ResearchConclusion",
    "ResearchError",
    "ResearchQuestion",
    "synthesize",
    "validate_reproduction",
]

from .evidence_contracts import (
    EvidenceGraph,
    EvidenceNode,
    ExperimentPlan,
    Outcome,
    ReproductionRecord,
    ResearchConclusion,
    ResearchError,
    ResearchQuestion,
    synthesize,
    validate_reproduction,
)

# VOL-249/250: authority-neutral bounded inquiry and causal simulation.
from .hypothesis_engine import (
    EvidenceDirection,
    EvidenceMode,
    Hypothesis,
    HypothesisAssessment,
    HypothesisComparison,
    HypothesisError,
    HypothesisEvidence,
    HypothesisLedger,
)
from .causal_knowledge import (
    CausalClaim,
    CausalGraph,
    CausalGraphSnapshot,
    CausalKnowledgeError,
    ClaimKind,
    InterventionResult,
)

__all__.extend((
    "EvidenceDirection",
    "EvidenceMode",
    "Hypothesis",
    "HypothesisAssessment",
    "HypothesisComparison",
    "HypothesisError",
    "HypothesisEvidence",
    "HypothesisLedger",
    "CausalClaim",
    "CausalGraph",
    "CausalGraphSnapshot",
    "CausalKnowledgeError",
    "ClaimKind",
    "InterventionResult",
))

from .game_design_probes import (
    DesignProbePlan,
    DesignProbePlanner,
    DesignProbeRequest,
    ProbeEvidenceStatus,
    ProbePlanningError,
)

__all__ += [
    "DesignProbePlan", "DesignProbePlanner", "DesignProbeRequest",
    "ProbeEvidenceStatus", "ProbePlanningError",
]
