"""Dragon Atlas source-only forensic inspection facade; imports are inert.

Authority remains with the canonical authenticated Mongo crawler and operator.
"""
from .frames import Anchor, Frame, FrameSet, bind_selected_frames
from .text_security import TextSecurityFinding, TextSecurityReport, scan_text_security
from .anchor_geometry import SourceGeometry, AnchorGeometry, measure_anchor_geometry
from .source_reuse import ReuseComponent, SourceReuseReport, analyze_source_reuse
from .objective_resilience import ObjectiveSensitivity, ObjectiveResilience, analyze_objective_resilience
from .boilerplate import BoilerplateFinding, BoilerplateReport, inspect_boilerplate
from .freshness import CaptureAgeFinding, CaptureAgeReport, inspect_capture_age
from .review_triage import ForensicReviewTask, ForensicReviewQueue, compile_forensic_review_queue
from .sentence_echo import SentenceEcho, SentenceEchoReport, inspect_sentence_echoes
from .active_content import ActiveContentFinding, ActiveContentReport, inspect_active_content
from .privacy_signals import PrivacySignal, PrivacySignalReport, inspect_privacy_signals
from .host_exposure import HostExposure, HostExposureReport, measure_host_exposure
from .polarity_screen import PolarityReviewLead, PolarityScreen, inspect_polarity_candidates
from .provenance_posture import ProvenanceFinding, ProvenancePosture, audit_capture_provenance
from .objective_grounding import ObjectiveGrounding, ObjectiveGroundingReport, inspect_objective_grounding
from .reference_concentration import CitationConcentration, CitationConcentrationReport, inspect_reference_concentration
from .consent_horizon import ConsentHorizon, inspect_consent_horizon
from .source_usage_map import SourceObjectiveUse, SourceUsageMap, compile_source_usage_map
from .research_gap_matrix import ResearchGap, ResearchGapMatrix, synthesize_research_gaps
from .context_budget_audit import ContextSourceBudget, ContextBudgetAudit, audit_context_budget
from .review_workload import HypotheticalReviewerSlot, ReviewCapacityPlan, plan_review_capacity
from .extraction_quality import ExtractionFinding, ExtractionQualityReport, inspect_extraction_quality
from .query_support_audit import QuerySupportFinding, QuerySupportAudit, audit_query_support
from .source_origin_audit import OriginFinding, SourceOriginAudit, audit_selected_origins
from .selection_fairness import SelectionFairnessFinding, SelectionFairnessAudit, measure_selection_fairness
from .risk_ablation import RiskAblationFinding, RiskAblationReport, simulate_risk_ablations
from .script_coverage import ScriptCoverageFinding, ScriptCoverageReport, inspect_script_coverage
from .trace import ForensicStage, chain_forensic_receipts, verify_forensic_stage_chain
from .assembly import AtlasForensics, compose_atlas_forensics, verify_atlas_forensics

__all__ = [name for name in globals() if not name.startswith("_")]
