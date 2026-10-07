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
