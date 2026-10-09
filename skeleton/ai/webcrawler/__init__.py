"""Policy-bound webcrawler plane for AI information gathering."""
from .core import CrawlBudget,CrawlDocument,CrawlEngine,CrawlPolicy,FrontierItem,InMemoryCrawlStore,canonicalize_url,extract_document
from .research import EvidenceObservation,EvidenceSet,ResearchQuery,frontier_priority
from .temporal import ChangeEvent,TemporalCorpus,TemporalVersion
from .storage import SqliteCrawlStore
from .governance import HostBudgetController,PromotionDecision,PromotionGate
from .ingestion import GovernedIngestor,IngestionReceipt
from .ingestion_registry import DurableIngestionRegistry,IngestionLease
from .outbox import IngestionOutbox,OutboxOperation
from .year_signals import YearSignalSeries,YearSignalDelta
from .decade_signals import DecadeSignalSeries,DecadeSignalDelta
from .regimes import RegimeDetector,Regime,ChangePoint
from .historical_bias import HistoricalBiasAnalyzer,HistoricalBias
from .regime_trajectory import RegimeTransition,classify_regime_transitions
from .contradiction_history import ContradictionPersistence,contradiction_persistence,persistent_contestation
from .session import ResearchSession,SessionLimits
from .recrawl import RecrawlItem,RecrawlScheduler
from .knowledge_bridge import CanonicalKnowledgeBridge,KnowledgeBridgeReceipt
from .traps import TrapDecision,TrapGuard
from .leases import Lease,SqliteLeaseStore
from .mime import ExtractedPayload,MimeExtractor
from .retrieval_bridge import CanonicalRetrievalBridge,RetrievalBridgeReceipt
from .claiming import ClaimedWork,FrontierClaimer
from .content_credentials import CredentialObservation,credential_trust_delta
from .dns_binding import ResolvedTarget,resolve_target,peer_is_planned
from .durable_frontier import DurableClaim,DurableFrontier
from .bound_http import SocketBoundFetcher,BoundConnectionError
__all__=[name for name in globals() if not name.startswith("_")]

from .temporal_semantics import TemporalSemantics,infer_temporal_semantics
from .uncertainty import Interval,deterministic_bootstrap,polarity_uncertainty
from .lag_signals import LagSignal,lag_scan
from .active_research import AcquisitionTarget,plan_acquisition

from .bitemporal import BitemporalFact
from .source_dependence import DependenceEdge,source_dependence,independent_host_count
from .temporal_scope import TemporalScope,filter_temporal
from .acquisition_queries import AcquisitionQuery,synthesize_acquisition_queries
from .regime_assurance import ChangePointDecision,gate_change_points

from .citation_lineage import CitationEdge,extract_citation_edges,citation_dependence
from .calibration import CalibrationReport,calibration_report
from .counterfactual import EvidenceInfluence,leave_one_out_influence
from .evidence_revision import RevisionReceipt,revision_receipt

from .shapley import SourceAttribution,approximate_shapley
from .stopping import ResearchStopDecision,decide_research_stop
from .temporal_retrieval import TemporalFragment,TemporalRetrievalCatalog

from .value_of_information import ResearchAction,ActionValue,rank_actions
from .sequential_evidence import SequentialDecision,sequential_bernoulli
from .source_quality import SourcePosterior,update_source_quality,conservative_quality
from .research_state import ResearchStateStore

from .information_gain import InformationGain,binary_entropy,expected_binary_information_gain
from .dependence_trust import ClusterTrust,dependence_adjusted_trust
from .action_learning import ActionEconomics,update_action_economics
from .research_learning import ResearchLearningStore
from .research_controller import ControllerCandidate,ControllerChoice,choose_next_action

from .dragon_events import DragonCrawlEvent,DragonEventStream
from .dragon_visual_state import DragonVisualState,visual_state
from .dragon_observer import DragonCrawlObserver
from .dragon_graph import CrawlGraphNode,CrawlGraphEdge,CrawlGraphProjection

# Lazy exported crawler-to-generation spine: keep durable crawler imports independent
# of the native model runtime and the optional external-generation boundary.
from importlib import import_module as _crawler_import_module
_SPINE_EXPORTS = {
    "CrawlRetrievalBridgeError": ".evidence_retrieval_bridge",
    "CrawlRetrievalRecord": ".evidence_retrieval_bridge",
    "bridge_crawl_document": ".evidence_retrieval_bridge",
    "CrawlContextBundle": ".context_bridge",
    "compile_crawl_context": ".context_bridge",
    "EvidenceGenerationError": ".generation_bridge",
    "EvidenceGenerationReceipt": ".generation_bridge",
    "EvidenceGenerationResult": ".generation_bridge",
    "generate_from_crawl_context": ".generation_bridge",
    "AssurancePolicy": ".dragon_provenance_assurance",
    "ProvenanceAssurance": ".dragon_provenance_assurance",
    "SourceCluster": ".dragon_provenance_assurance",
    "ClusterHoldout": ".dragon_provenance_assurance",
    "ResearchNextAction": ".dragon_provenance_assurance",
    "assure_crawler_evidence": ".dragon_provenance_assurance",
    "CustodyPromotionReview": ".dragon_provenance_promotion",
    "assess_custodied_promotion": ".dragon_provenance_promotion",
    "CapturedSource": ".dragon_crawl_custody",
    "LocatedReading": ".dragon_crawl_custody",
    "CrawlCustodyBundle": ".dragon_crawl_custody",
    "CustodyPolicy": ".dragon_crawl_custody",
    "CapturedCrawlReview": ".dragon_crawl_custody",
    "bind_crawl_evidence": ".dragon_crawl_custody",
    "assure_captured_crawl": ".dragon_crawl_custody",
    "SourceChange": ".dragon_crawl_revision",
    "ReadingDisposition": ".dragon_crawl_revision",
    "SourceRevisionDelta": ".dragon_crawl_revision",
    "ReadingRevalidation": ".dragon_crawl_revision",
    "RevisionRevalidation": ".dragon_crawl_revision",
    "compare_crawl_revisions": ".dragon_crawl_revision",
    "revision_report_fingerprint": ".dragon_crawl_revision",
    "RevisionEntry": ".dragon_revision_journal",
    "RevisionJournal": ".dragon_revision_journal",
}

def __getattr__(name: str):
    target = _SPINE_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    result = getattr(_crawler_import_module(target, __name__), name)
    globals()[name] = result
    return result

__all__ += list(_SPINE_EXPORTS)
