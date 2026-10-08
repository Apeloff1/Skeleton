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
    "RightsGrant": ".dragon_mission_quality",
    "TextRisk": ".dragon_mission_quality",
    "TextSpan": ".dragon_mission_quality",
    "RankedPassage": ".dragon_mission_quality",
    "DuplicateGroup": ".dragon_mission_quality",
    "InformationQuality": ".dragon_mission_quality",
    "require_training_grant": ".dragon_mission_quality",
    "scan_untrusted_instructions": ".dragon_mission_quality",
    "mask_personal_data": ".dragon_mission_quality",
    "segment_passages": ".dragon_mission_quality",
    "rank_query_passages": ".dragon_mission_quality",
    "exact_revision_groups": ".dragon_mission_quality",
    "near_duplicate_groups": ".dragon_mission_quality",
    "measure_information_quality": ".dragon_mission_quality",
    "locate_uncertainty_cues": ".dragon_mission_quality",
    "extract_citation_candidates": ".dragon_mission_quality",
    "CuratedFragment": ".dragon_mission_token_feed",
    "EncodedFragment": ".dragon_mission_token_feed",
    "TokenWindow": ".dragon_mission_token_feed",
    "DatasetAssignment": ".dragon_mission_token_feed",
    "YearTaggedWindow": ".dragon_mission_token_feed",
    "TrainingManifest": ".dragon_mission_token_feed",
    "curate_training_fragment": ".dragon_mission_token_feed",
    "encode_verified_tokens": ".dragon_mission_token_feed",
    "pack_token_windows": ".dragon_mission_token_feed",
    "assign_dependency_splits": ".dragon_mission_token_feed",
    "balance_decade_windows": ".dragon_mission_token_feed",
    "compile_training_manifest": ".dragon_mission_token_feed",
    "AcquisitionCandidate": ".dragon_mission_scheduler",
    "PrioritizedAcquisition": ".dragon_mission_scheduler",
    "HostDispatch": ".dragon_mission_scheduler",
    "RecrawlSource": ".dragon_mission_scheduler",
    "RecrawlDue": ".dragon_mission_scheduler",
    "MissionStopDecision": ".dragon_mission_scheduler",
    "rank_acquisition_candidates": ".dragon_mission_scheduler",
    "allocate_host_dispatches": ".dragon_mission_scheduler",
    "plan_adaptive_recrawls": ".dragon_mission_scheduler",
    "decide_mission_stop": ".dragon_mission_scheduler",
    "MissionCapability": ".dragon_mission_catalog",
    "CAPABILITY_CATALOG": ".dragon_mission_catalog",
    "resolve_mission_capability": ".dragon_mission_catalog",
    "describe_mission_capabilities": ".dragon_mission_catalog",
    "GameSource": ".game_knowledge_acquisition",
    "KnowledgePassage": ".game_knowledge_acquisition",
    "GameParameter": ".game_knowledge_acquisition",
    "EngineSymbol": ".game_knowledge_acquisition",
    "plan_game_research": ".game_knowledge_acquisition",
    "discover_game_research": ".game_knowledge_acquisition",
    "prioritize_game_sources": ".game_knowledge_acquisition",
    "queue_game_sources": ".game_knowledge_acquisition",
    "acquire_game_documents": ".game_knowledge_acquisition",
    "extract_game_sections": ".game_knowledge_acquisition",
    "extract_game_mechanics": ".game_knowledge_acquisition",
    "extract_engine_symbols": ".game_knowledge_acquisition",
    "extract_game_parameters": ".game_knowledge_acquisition",
    "extract_design_guidance": ".game_knowledge_acquisition",
    "official_game_documentation": ".game_knowledge_acquisition",
    "enqueue_official_game_docs": ".game_knowledge_acquisition",
    "GameKnowledgeHit": ".game_knowledge_index",
    "ContradictionCandidate": ".game_knowledge_index",
    "KnowledgeGap": ".game_knowledge_index",
    "GameKnowledgeIndex": ".game_knowledge_index",
    "GameBlueprint": ".game_knowledge_design",
    "LevelMetrics": ".game_knowledge_design",
    "propose_game_blueprint": ".game_knowledge_design",
    "select_game_mechanics": ".game_knowledge_design",
    "resolve_mechanic_dependencies": ".game_knowledge_design",
    "budget_game_mechanics": ".game_knowledge_design",
    "design_player_physics": ".game_knowledge_design",
    "design_level_geometry": ".game_knowledge_design",
    "estimate_jump_reach": ".game_knowledge_design",
    "find_level_route": ".game_knowledge_design",
    "populate_game_level": ".game_knowledge_design",
    "analyze_level_playability": ".game_knowledge_design",
    "CompiledGame": ".game_playable_builder",
    "compile_scene_entities": ".game_playable_builder",
    "compile_tile_collision": ".game_playable_builder",
    "compile_input_controls_js": ".game_playable_builder",
    "compile_physics_system_js": ".game_playable_builder",
    "compile_enemy_behaviors_js": ".game_playable_builder",
    "compile_gameplay_system_js": ".game_playable_builder",
    "compile_camera_system_js": ".game_playable_builder",
    "compile_rendering_system_js": ".game_playable_builder",
    "build_playable_web_game": ".game_playable_builder",
    "export_playable_game_archive": ".game_playable_builder",
    "GodotProject": ".game_godot_export",
    "compile_godot_project": ".game_godot_export",
    "export_godot_game_archive": ".game_godot_export",
    "GameKnowledgeBuild": ".game_builder_knowledge_runtime",
    "KnowledgeDrivenGameBuilder": ".game_builder_knowledge_runtime",
    "import_research_captures": ".game_builder_cli",
}

# Expand the public knowledge-to-game-building API with one hundred
# introspectable, *implemented* capabilities; modules remain lazy-loaded.
from .game_scale_catalog import MILESTONES as GAME_SCALE_MILESTONES
from .game_scale_catalog import game_milestone_by_number, grouped_game_milestones
_SPINE_EXPORTS.update({
    milestone.operation: milestone.module for milestone in GAME_SCALE_MILESTONES
})
_SPINE_EXPORTS.update({
    "generate_level_studio": ".game_scale_studio",
    "EnhancedGame": ".game_scale_integration",
    "build_enhanced_game": ".game_scale_integration",
    "Room": ".game_scale_world",
    "WorldRegion": ".game_scale_world",
    "AgentIntent": ".game_scale_npc_ai",
    "Weapon": ".game_scale_combat",
    "Fighter": ".game_scale_combat",
    "Projectile": ".game_scale_combat",
    "Status": ".game_scale_combat",
    "Item": ".game_scale_economy",
    "Inventory": ".game_scale_economy",
    "Recipe": ".game_scale_economy",
    "TradingPost": ".game_scale_economy",
    "Quest": ".game_scale_story",
    "Objective": ".game_scale_story",
    "QuestProgress": ".game_scale_story",
    "StoryState": ".game_scale_story",
    "DialogueNode": ".game_scale_story",
    "DialogueChoice": ".game_scale_story",
    "Sprite": ".game_scale_assets",
    "PlayBalance": ".game_scale_balancing",
    "EditorHistory": ".game_scale_editor",
    "open_editor_history": ".game_scale_editor",
    "record_editor_edit": ".game_scale_editor",
    "LearningStep": ".game_scale_research",
    "Campaign": ".game_scale_campaign",
    "Chapter": ".game_scale_campaign",
    "HeroProgress": ".game_scale_campaign",
    "decode_campaign_save": ".game_scale_campaign",
    "restore_story_slot": ".game_scale_story",
})

def __getattr__(name: str):
    target = _SPINE_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    result = getattr(_crawler_import_module(target, __name__), name)
    globals()[name] = result
    return result

__all__ += list(_SPINE_EXPORTS)
