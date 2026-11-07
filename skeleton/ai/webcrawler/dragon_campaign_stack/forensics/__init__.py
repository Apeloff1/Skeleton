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
from .trace import ForensicStage, chain_forensic_receipts, verify_forensic_stage_chain
from .assembly import AtlasForensics, compose_atlas_forensics, verify_atlas_forensics

__all__ = [name for name in globals() if not name.startswith("_")]
