"""Governed dual-rival game-builder runtime contracts.

The package contains deterministic control-plane primitives only. Model/provider
execution remains outside the authority boundary and must enter through governed
candidate, canon, rights, atom-lineage, and evidence contracts.
"""

from .atomizer import ArtifactAtom, AtomGraph, AtomGraphError, AtomSourceBinding
from .canon import CanonAssertion, CanonError, CanonLedger, CharacterKnowledge
from .contracts import (
    ArtifactIdentity,
    Candidate,
    Challenge,
    EffortMode,
    EvaluatorProvenance,
    GateResult,
    PromotionReceipt,
    ProducerProvenance,
    Rival,
    Stage,
    canonical_digest,
)
from .dual_rival_forge import DualRivalForge, ForgeStateError
from .control_plane import ControlPlaneError, ControlledStatus, ForgeControlPlane
from .experience_eval import (
    EXPERIENCE_METRICS,
    ExperienceDefect,
    ExperienceEvaluationError,
    ExperienceObservation,
    ExperiencePromotionDecision,
    ExperienceReport,
    build_experience_report,
    evaluate_experience_promotion,
    normalize_experience_metrics,
)
from .evaluation import (
    EvaluationError,
    EvaluationPanel,
    JudgeVerdict,
    PanelDecision,
    blind_candidate_token,
)
from .quality_debt import (
    DebtItem,
    DebtSeverity,
    QualityDebtError,
    QualityDebtLedger,
)
from .resource_governor import (
    ResourceDelta,
    ResourceEnvelope,
    ResourceGovernor,
    ResourceLimitError,
    ResourceSnapshot,
)
from .resilience import (
    DissentLedger,
    ImpactCalibrationReceipt,
    ImpactGraph,
    Invariant,
    InvariantRegistry,
    InvariantRevisionReceipt,
    NoveltyRecord,
    NoveltyReservoir,
    Objection,
    ResilienceError,
)
from .release import (
    CriticalGateQualification,
    FamilyQualification,
    ForgeReleaseBinding,
    GoldMasterBundle,
    GoldMasterTribunal,
    GoldMasterVerdict,
    ReleaseArbitrationError,
    TribunalVote,
)
from .deep_assurance import (
    ClosureCertificate,
    ComplexityDecision,
    ComplexityGovernor,
    ComplexitySnapshot,
    ConstraintProofSet,
    ConstraintResult,
    DeepAssuranceError,
    EvidenceMerkleLedger,
    GranularityCoverage,
    HermeticTransformRegistry,
    IntentInvariant,
    IntentPreservationGate,
    InteractionMatrix,
    KnowledgeIngestionFirewall,
    KnowledgeSource,
    MentalModelProbe,
    PlayerMentalModelGate,
    ProjectResurrectionRegistry,
    RareEventObservation,
    RequirementClosureLedger,
    RequirementProof,
    ResurrectionPoint,
    ResurrectionVerification,
    TailRiskLab,
    TelemetryAggregate,
    TelemetryFeedbackGate,
    TransformReceipt,
)
from .evaluator_provenance import (
    EvaluatorProvenanceBindingError,
    evaluator_provenance_from_canonical_execution,
    gate_result_from_canonical_execution,
    judge_verdict_from_canonical_execution,
)
from .producer_provenance import (
    ProducerProvenanceBindingError,
    candidate_from_canonical_execution,
    producer_provenance_from_canonical_execution,
)
from .rights import (
    IncorporationDecision,
    RightsError,
    RightsLedger,
    RightsState,
    SimilarityFinding,
    SimilarityRisk,
    SourceRecord,
    UseKind,
)

__all__ = [
    "ArtifactAtom",
    "ArtifactIdentity",
    "AtomGraph",
    "AtomGraphError",
    "AtomSourceBinding",
    "Candidate",
    "CanonAssertion",
    "CanonError",
    "CanonLedger",
    "Challenge",
    "CharacterKnowledge",
    "DualRivalForge",
    "EffortMode",
    "EvaluatorProvenance",
    "EvaluatorProvenanceBindingError",
    "evaluator_provenance_from_canonical_execution",
    "gate_result_from_canonical_execution",
    "judge_verdict_from_canonical_execution",
    "ForgeStateError",
    "GateResult",
    "IncorporationDecision",
    "PromotionReceipt",
    "ProducerProvenance",
    "ProducerProvenanceBindingError",
    "candidate_from_canonical_execution",
    "producer_provenance_from_canonical_execution",
    "RightsError",
    "RightsLedger",
    "RightsState",
    "Rival",
    "SimilarityFinding",
    "SimilarityRisk",
    "SourceRecord",
    "Stage",
    "UseKind",
    "canonical_digest",
    "ControlPlaneError",
    "ControlledStatus",
    "DebtItem",
    "DebtSeverity",
    "EvaluationError",
    "normalize_experience_metrics",
    "evaluate_experience_promotion",
    "build_experience_report",
    "ExperienceReport",
    "ExperiencePromotionDecision",
    "ExperienceObservation",
    "ExperienceEvaluationError",
    "ExperienceDefect",
    "EXPERIENCE_METRICS",
    "EvaluationPanel",
    "ForgeControlPlane",
    "JudgeVerdict",
    "PanelDecision",
    "QualityDebtError",
    "QualityDebtLedger",
    "ResourceDelta",
    "ResourceEnvelope",
    "ResourceGovernor",
    "ResourceLimitError",
    "ResourceSnapshot",
    "blind_candidate_token",
    "DissentLedger",
    "ImpactCalibrationReceipt",
    "ImpactGraph",
    "Invariant",
    "InvariantRegistry",
    "InvariantRevisionReceipt",
    "NoveltyRecord",
    "NoveltyReservoir",
    "Objection",
    "ResilienceError",
    "FamilyQualification",
    "ForgeReleaseBinding",
    "GoldMasterBundle",
    "GoldMasterTribunal",
    "GoldMasterVerdict",
    "ReleaseArbitrationError",
    "TribunalVote",
    "CriticalGateQualification",
    "ClosureCertificate",
    "ComplexityDecision",
    "ComplexityGovernor",
    "ComplexitySnapshot",
    "ConstraintProofSet",
    "ConstraintResult",
    "DeepAssuranceError",
    "EvidenceMerkleLedger",
    "GranularityCoverage",
    "HermeticTransformRegistry",
    "IntentInvariant",
    "IntentPreservationGate",
    "InteractionMatrix",
    "KnowledgeIngestionFirewall",
    "KnowledgeSource",
    "MentalModelProbe",
    "PlayerMentalModelGate",
    "ProjectResurrectionRegistry",
    "RareEventObservation",
    "RequirementClosureLedger",
    "RequirementProof",
    "ResurrectionPoint",
    "ResurrectionVerification",
    "TailRiskLab",
    "TelemetryAggregate",
    "TelemetryFeedbackGate",
    "TransformReceipt",
]


# The persistent knowledge library is loaded only when requested. It never
# implicitly creates a database, crawls a URL, or promotes a game design.
from importlib import import_module as _game_builder_import_module

_KNOWLEDGE_EXPORTS = {
    "EvolutionPractice": ".evolution_practice",
    "EvolutionPracticePack": ".evolution_practice",
    "practice_evolution_games": ".evolution_practice",
    "CreditsError": ".asset_credits",
    "AttributionEntry": ".asset_credits",
    "CreditsBundle": ".asset_credits",
    "compile_game_credits": ".asset_credits",
    "export_game_credits": ".asset_credits",
    "NativeReleaseGateReport": ".release_pipeline",
    "run_native_release_gate": ".release_pipeline",
    "SegaBuildEvidenceError": ".sega_reproducibility",
    "SegaReproducibilityReceipt": ".sega_reproducibility",
    "verify_rebuilt_sega_cartridge": ".sega_reproducibility",
    "verify_separate_authoring_runs": ".sega_reproducibility",
    "RetroArtifactError": ".native_retro_artifact",
    "RetroArtifactReceipt": ".native_retro_artifact",
    "inspect_original_retro_artifact": ".native_retro_artifact",
    "ExecutableFormatError": ".native_binary_structure",
    "ExecutableStructureReceipt": ".native_binary_structure",
    "verify_native_executable_structure": ".native_binary_structure",
    "StructurallyVerifiedNativeReleaseReport": ".release_pipeline",
    "run_structurally_verified_native_release_gate": ".release_pipeline",
    "NativeIntakeError": ".native_release_intake",
    "NativeIntakeReceipt": ".native_release_intake",
    "verify_native_release_intake": ".native_release_intake",
    "SignedReviewerRegistry": ".release_trust_anchor",
    "PinnedReviewerResult": ".release_trust_anchor",
    "evaluate_pinned_independent_review": ".release_trust_anchor",
    "PinnedNativeReleaseGateReport": ".release_pipeline",
    "run_pinned_native_release_gate": ".release_pipeline",
    "ReleaseReviewError": ".release_assurance",
    "ReleaseChannel": ".release_assurance",
    "ReviewRole": ".release_assurance",
    "ReviewDomain": ".release_assurance",
    "ReviewDecision": ".release_assurance",
    "ReleaseReadiness": ".release_assurance",
    "ReleaseCandidate": ".release_assurance",
    "TrustedReviewer": ".release_assurance",
    "ReviewAttestation": ".release_assurance",
    "ReleaseReviewReceipt": ".release_assurance",
    "evaluate_independent_review": ".release_assurance",
    "MediaScreenError": ".media_similarity",
    "MediaFingerprint": ".media_similarity",
    "MediaMatchEvidence": ".media_similarity",
    "fingerprint_image": ".media_similarity",
    "fingerprint_wav": ".media_similarity",
    "compare_media": ".media_similarity",
    "OriginalityError": ".plagiarism_guard",
    "AttributionStatus": ".plagiarism_guard",
    "UseBasis": ".plagiarism_guard",
    "AssetDisposition": ".plagiarism_guard",
    "OriginalityDisposition": ".plagiarism_guard",
    "AssetDeclaration": ".plagiarism_guard",
    "ExpressionSample": ".plagiarism_guard",
    "ExpressiveOverlap": ".plagiarism_guard",
    "OriginalityReport": ".plagiarism_guard",
    "find_expression_overlap": ".plagiarism_guard",
    "audit_game_originality": ".plagiarism_guard",
    "compile_originality_gated_desktop": ".legal_native_export",
    "ClearedSourceExportError": ".legal_native_export",
    "LegalNativeDesktopSource": ".legal_native_export",
    "compile_rights_aware_desktop": ".legal_native_export",
    "export_rights_aware_desktop": ".legal_native_export",
    "HistoricalRightsCandidate": ".legal_census",
    "HistoricalRightsCensus": ".legal_census",
    "catalog_rights_census": ".legal_census",
    "HomebrewPolicyError": ".legal_paths",
    "Jurisdiction": ".legal_paths",
    "CreativeMode": ".legal_paths",
    "LegalDisposition": ".legal_paths",
    "MaterialKind": ".legal_paths",
    "MaterialRecord": ".legal_paths",
    "HardwareAccessFacts": ".legal_paths",
    "InteroperabilityFacts": ".legal_paths",
    "HomebrewLegalRequest": ".legal_paths",
    "HomebrewLegalAssessment": ".legal_paths",
    "legal_authorities": ".legal_paths",
    "assess_homebrew": ".legal_paths",
    "hardware_rights_matrix": ".legal_paths",
    "RightsAwarePortProposal": ".legal_port_bridge",
    "propose_rights_aware_port": ".legal_port_bridge",
    "MachineArchiveError": ".archive_import",
    "MachineRecord": ".archive_import",
    "MachineSnapshot": ".archive_import",
    "import_mame_listxml": ".archive_import",
    "export_review_queue": ".archive_import",
    "GameEvolutionError": ".evolution_archive",
    "EvolutionNode": ".evolution_archive",
    "EvolutionArchive": ".evolution_archive",
    "EvolutionStage": ".evolution_archive",
    "EvolutionCampaign": ".evolution_archive",
    "parse_evolution_archive": ".evolution_archive",
    "default_evolution_archive": ".evolution_archive",
    "plan_evolution_campaign": ".evolution_archive",
    "archive_coverage_report": ".evolution_archive",
    "GameBoyColorSourceError": ".game_boy_color_native_export",
    "GameBoyColorSourceProject": ".game_boy_color_native_export",
    "compile_native_game_boy_color": ".game_boy_color_native_export",
    "export_native_game_boy_color": ".game_boy_color_native_export",
    "GameBoySourceError": ".game_boy_native_export",
    "GameBoySourceProject": ".game_boy_native_export",
    "compile_native_game_boy": ".game_boy_native_export",
    "export_native_game_boy": ".game_boy_native_export",
    "SMSNativeError": ".sms_native_export",
    "SMSSourceProject": ".sms_native_export",
    "compile_native_sms": ".sms_native_export",
    "export_native_sms": ".sms_native_export",
    "make_sms": ".sms_rom",
    "verify_sms": ".sms_rom",
    "VectrexNativeError": ".vectrex_native_export",
    "VectrexSourceProject": ".vectrex_native_export",
    "compile_native_vectrex": ".vectrex_native_export",
    "export_native_vectrex": ".vectrex_native_export",
    "verify_vectrex": ".vectrex_rom",
    "ColecoNativeError": ".coleco_native_export",
    "ColecoSourceProject": ".coleco_native_export",
    "compile_native_coleco": ".coleco_native_export",
    "export_native_coleco": ".coleco_native_export",
    "make_col": ".coleco_rom",
    "verify_col": ".coleco_rom",
    "MSX1NativeError": ".msx1_native_export",
    "MSX1SourceProject": ".msx1_native_export",
    "compile_native_msx1": ".msx1_native_export",
    "export_native_msx1": ".msx1_native_export",
    "make_msx1_rom": ".msx1_rom",
    "verify_msx1_rom": ".msx1_rom",
    "SpectrumNativeError": ".spectrum_native_export",
    "SpectrumSourceProject": ".spectrum_native_export",
    "compile_native_spectrum": ".spectrum_native_export",
    "export_native_spectrum": ".spectrum_native_export",
    "make_tape": ".spectrum_tap",
    "verify_tape": ".spectrum_tap",
    "Apple2NativeError": ".apple2_native_export",
    "Apple2SourceProject": ".apple2_native_export",
    "compile_native_apple2": ".apple2_native_export",
    "export_native_apple2": ".apple2_native_export",
    "Atari8BitNativeError": ".atari8_native_export",
    "Atari8BitSourceProject": ".atari8_native_export",
    "compile_native_atari8": ".atari8_native_export",
    "export_native_atari8": ".atari8_native_export",
    "NativeDOSError": ".dos_native_export",
    "NativeDOSSourceProject": ".dos_native_export",
    "compile_native_dos": ".dos_native_export",
    "export_native_dos": ".dos_native_export",
    "build_native_evolution": ".native_evolution_cli",
    "NativePortfolioError": ".native_portfolio_cli",
    "compile_native_portfolio": ".native_portfolio_cli",
    "NativeC64Error": ".c64_native_export",
    "NativeC64SourceProject": ".c64_native_export",
    "compile_native_c64": ".c64_native_export",
    "export_native_c64": ".c64_native_export",
    "GameBoyReplayError": ".game_boy_memory_replay",
    "plan_game_boy_memory_replay": ".game_boy_memory_replay",
    "export_game_boy_memory_replay": ".game_boy_memory_replay",
    "NativeNESError": ".nes_native_export",
    "NativeNESSourceProject": ".nes_native_export",
    "compile_native_nes": ".nes_native_export",
    "export_native_nes": ".nes_native_export",
    "EvolutionNativeStage": ".evolution_native_sources",
    "EvolutionNativeSourcePack": ".evolution_native_sources",
    "compile_evolution_native_sources": ".evolution_native_sources",
    "export_evolution_native_sources": ".evolution_native_sources",
    "NativeDesktopExportError": ".desktop_native_export",
    "NativeDesktopSourceProject": ".desktop_native_export",
    "compile_native_desktop": ".desktop_native_export",
    "export_native_desktop_source": ".desktop_native_export",
    "editor_platform_options": ".editor_platforms",
    "editor_portability_context": ".editor_platforms",
    "editor_platform_form": ".editor_platforms",
    "editor_progressive_route_preview": ".editor_platforms",
    "PlatformProfile": ".platform_registry",
    "PlatformRegistry": ".platform_registry",
    "PlatformRegistryError": ".platform_registry",
    "default_registry": ".platform_registry",
    "lookup_platform": ".platform_registry",
    "list_platforms": ".platform_registry",
    "parse_registry": ".platform_registry",
    "HomebrewSource": ".port_planner",
    "PortMode": ".port_planner",
    "PortRequest": ".port_planner",
    "PortAction": ".port_planner",
    "PortBlueprint": ".port_planner",
    "ProgressivePortHop": ".port_planner",
    "ProgressivePortRoute": ".port_planner",
    "PortPlanningError": ".port_planner",
    "compile_port": ".port_planner",
    "compile_port_route": ".port_planner",
    "compile_progressive_port_route": ".port_planner",
    "KnowledgeError": ".reviewed_knowledge",
    "KnowledgePolicy": ".reviewed_knowledge",
    "ReviewedNote": ".reviewed_knowledge",
    "ReviewedDocument": ".reviewed_knowledge",
    "RevisionReceipt": ".reviewed_knowledge",
    "KnowledgeHit": ".reviewed_knowledge",
    "KnowledgeBrief": ".reviewed_knowledge",
    "ReviewedKnowledgeStore": ".reviewed_knowledge",
    "ResearchHandoffError": ".knowledge_rights_bridge",
    "ClearedResearchSource": ".knowledge_rights_bridge",
    "ClearedResearchPacket": ".knowledge_rights_bridge",
    "clear_research_for_design": ".knowledge_rights_bridge",
    "require_cleared_research_current": ".knowledge_rights_bridge",
    "GameBuildIntent": ".playable_world",
    "TileLevel": ".playable_world",
    "PlayableWorld": ".playable_world",
    "PlayableWorldError": ".playable_world",
    "generate_playable_world": ".playable_world",
    "solve_safe_path": ".playable_world",
    "GameplayError": ".playable_simulation",
    "PlayState": ".playable_simulation",
    "ActionReceipt": ".playable_simulation",
    "GameReplay": ".playable_simulation",
    "initial_state": ".playable_simulation",
    "advance": ".playable_simulation",
    "play_actions": ".playable_simulation",
    "verify_replay": ".playable_simulation",
    "demonstrate_solvable": ".playable_simulation",
    "PlayableHTML": ".playable_export",
    "PlayableExportError": ".playable_export",
    "render_playable_world": ".playable_export",
    "write_playable_html": ".playable_export",
    "PlayableCompilationError": ".playable_compiler",
    "CompiledPlayableProject": ".playable_compiler",
    "compile_original_game": ".playable_compiler",
    "compile_authored_game": ".playable_compiler",
    "compile_game_from_reviewed_research": ".playable_compiler",
    "export_compiled_project": ".playable_compiler",
    "PlayabilityAnalysisError": ".playability_analysis",
    "LevelExperience": ".playability_analysis",
    "PlayabilityFinding": ".playability_analysis",
    "PlayabilityReport": ".playability_analysis",
    "CohortExperience": ".playability_analysis",
    "analyze_replay": ".playability_analysis",
    "aggregate_playability": ".playability_analysis",
    "DualRuntimeExportError": ".dual_runtime_export",
    "DualRuntimePackage": ".dual_runtime_export",
    "render_dual_runtime_package": ".dual_runtime_export",
    "export_dual_runtime_package": ".dual_runtime_export",
    "AuthoredGameError": ".authored_tiles",
    "read_authored_document": ".authored_tiles",
    "compile_authored_world": ".authored_tiles",
    "compile_authored_document": ".authored_tiles",
    "ToolFabric": ".studio_tool_fabric",
    "ToolSpec": ".studio_tool_fabric",
    "ToolRequest": ".studio_tool_fabric",
    "ToolPlan": ".studio_tool_fabric",
    "Actor": ".studio_tool_fabric",
    "Phase": ".studio_tool_fabric",
    "Access": ".studio_tool_fabric",
    "ToolFabricError": ".studio_tool_fabric",
    "MirrorProbe": ".mirror_room_runtime",
    "MirrorReport": ".mirror_room_runtime",
    "MirrorRoomError": ".mirror_room_runtime",
    "review_playable_project": ".mirror_room_runtime",
    "ConsumerReview": ".original_game_studio",
    "StudioRun": ".original_game_studio",
    "StudioStage": ".original_game_studio",
    "CompanionPractice": ".original_game_studio",
    "StudioError": ".original_game_studio",
    "run_original_game_studio": ".original_game_studio",
    "export_studio_run": ".original_game_studio",
    "SignedReleaseEvidence": ".consumer_release_assurance",
    "TrustedReviewer": ".consumer_release_assurance",
    "ConsumerAssurance": ".consumer_release_assurance",
    "ReleaseEvidenceError": ".consumer_release_assurance",
    "EvidenceKind": ".consumer_release_assurance",
    "ReviewerRole": ".consumer_release_assurance",
    "assess_consumer_release": ".consumer_release_assurance",
    "ExecutionPlaneError": ".studio_execution_plane",
    "ExecutedToolReceipt": ".studio_execution_plane",
    "ExecutionOutcome": ".studio_execution_plane",
    "execute_local_tool_plan": ".studio_execution_plane",
    "CompanionCurriculumError": ".companion_curriculum",
    "PracticeInsight": ".companion_curriculum",
    "plan_original_companion_intents": ".companion_curriculum",
    "measure_original_practice": ".companion_curriculum",
    "validate_practice_cohort": ".companion_curriculum",
    "TiledImportError": ".tiled_map_import",
    "TiledConversion": ".tiled_map_import",
    "import_tiled_levels": ".tiled_map_import",
    "write_tiled_authored_json": ".tiled_map_import",
    "StoryError": ".living_story_runtime",
    "StoryIntent": ".living_story_runtime",
    "StoryWorld": ".living_story_runtime",
    "StoryState": ".living_story_runtime",
    "StoryReplay": ".living_story_runtime",
    "original_story_world": ".living_story_runtime",
    "npc_region": ".living_story_runtime",
    "first_story_state": ".living_story_runtime",
    "story_choices": ".living_story_runtime",
    "story_step": ".living_story_runtime",
    "story_play": ".living_story_runtime",
    "story_verify": ".living_story_runtime",
    "demonstrate_story": ".living_story_runtime",
    "dialogue_line": ".living_story_runtime",
    "StoryExportError": ".living_story_export",
    "StoryPackage": ".living_story_export",
    "render_story_package": ".living_story_export",
    "StoryMirrorError": ".living_story_mirror",
    "StoryMirrorReport": ".living_story_mirror",
    "review_living_story": ".living_story_mirror",
    "StoryAuthoringError": ".living_story_authoring",
    "AuthoredStory": ".living_story_authoring",
    "derive_original_story_intent": ".living_story_authoring",
    "blueprint_document": ".living_story_authoring",
    "compile_authored_story": ".living_story_authoring",
    "read_story_blueprint": ".living_story_authoring",
}


def _load_trusted_lazy_module(module: str):
    """Import from the repository-owned export map using only literal targets."""
    if module == ".apple2_native_export":
        return _game_builder_import_module(".apple2_native_export", __name__)
    if module == ".archive_import":
        return _game_builder_import_module(".archive_import", __name__)
    if module == ".asset_credits":
        return _game_builder_import_module(".asset_credits", __name__)
    if module == ".atari8_native_export":
        return _game_builder_import_module(".atari8_native_export", __name__)
    if module == ".authored_tiles":
        return _game_builder_import_module(".authored_tiles", __name__)
    if module == ".c64_native_export":
        return _game_builder_import_module(".c64_native_export", __name__)
    if module == ".coleco_native_export":
        return _game_builder_import_module(".coleco_native_export", __name__)
    if module == ".coleco_rom":
        return _game_builder_import_module(".coleco_rom", __name__)
    if module == ".companion_curriculum":
        return _game_builder_import_module(".companion_curriculum", __name__)
    if module == ".consumer_release_assurance":
        return _game_builder_import_module(".consumer_release_assurance", __name__)
    if module == ".desktop_native_export":
        return _game_builder_import_module(".desktop_native_export", __name__)
    if module == ".dos_native_export":
        return _game_builder_import_module(".dos_native_export", __name__)
    if module == ".dual_runtime_export":
        return _game_builder_import_module(".dual_runtime_export", __name__)
    if module == ".editor_platforms":
        return _game_builder_import_module(".editor_platforms", __name__)
    if module == ".evolution_archive":
        return _game_builder_import_module(".evolution_archive", __name__)
    if module == ".evolution_native_sources":
        return _game_builder_import_module(".evolution_native_sources", __name__)
    if module == ".evolution_practice":
        return _game_builder_import_module(".evolution_practice", __name__)
    if module == ".game_boy_color_native_export":
        return _game_builder_import_module(".game_boy_color_native_export", __name__)
    if module == ".game_boy_memory_replay":
        return _game_builder_import_module(".game_boy_memory_replay", __name__)
    if module == ".game_boy_native_export":
        return _game_builder_import_module(".game_boy_native_export", __name__)
    if module == ".knowledge_rights_bridge":
        return _game_builder_import_module(".knowledge_rights_bridge", __name__)
    if module == ".legal_census":
        return _game_builder_import_module(".legal_census", __name__)
    if module == ".legal_native_export":
        return _game_builder_import_module(".legal_native_export", __name__)
    if module == ".legal_paths":
        return _game_builder_import_module(".legal_paths", __name__)
    if module == ".legal_port_bridge":
        return _game_builder_import_module(".legal_port_bridge", __name__)
    if module == ".living_story_authoring":
        return _game_builder_import_module(".living_story_authoring", __name__)
    if module == ".living_story_export":
        return _game_builder_import_module(".living_story_export", __name__)
    if module == ".living_story_mirror":
        return _game_builder_import_module(".living_story_mirror", __name__)
    if module == ".living_story_runtime":
        return _game_builder_import_module(".living_story_runtime", __name__)
    if module == ".media_similarity":
        return _game_builder_import_module(".media_similarity", __name__)
    if module == ".mirror_room_runtime":
        return _game_builder_import_module(".mirror_room_runtime", __name__)
    if module == ".msx1_native_export":
        return _game_builder_import_module(".msx1_native_export", __name__)
    if module == ".msx1_rom":
        return _game_builder_import_module(".msx1_rom", __name__)
    if module == ".native_binary_structure":
        return _game_builder_import_module(".native_binary_structure", __name__)
    if module == ".native_evolution_cli":
        return _game_builder_import_module(".native_evolution_cli", __name__)
    if module == ".native_portfolio_cli":
        return _game_builder_import_module(".native_portfolio_cli", __name__)
    if module == ".native_release_intake":
        return _game_builder_import_module(".native_release_intake", __name__)
    if module == ".native_retro_artifact":
        return _game_builder_import_module(".native_retro_artifact", __name__)
    if module == ".nes_native_export":
        return _game_builder_import_module(".nes_native_export", __name__)
    if module == ".original_game_studio":
        return _game_builder_import_module(".original_game_studio", __name__)
    if module == ".plagiarism_guard":
        return _game_builder_import_module(".plagiarism_guard", __name__)
    if module == ".platform_registry":
        return _game_builder_import_module(".platform_registry", __name__)
    if module == ".playability_analysis":
        return _game_builder_import_module(".playability_analysis", __name__)
    if module == ".playable_compiler":
        return _game_builder_import_module(".playable_compiler", __name__)
    if module == ".playable_export":
        return _game_builder_import_module(".playable_export", __name__)
    if module == ".playable_simulation":
        return _game_builder_import_module(".playable_simulation", __name__)
    if module == ".playable_world":
        return _game_builder_import_module(".playable_world", __name__)
    if module == ".port_planner":
        return _game_builder_import_module(".port_planner", __name__)
    if module == ".release_assurance":
        return _game_builder_import_module(".release_assurance", __name__)
    if module == ".release_pipeline":
        return _game_builder_import_module(".release_pipeline", __name__)
    if module == ".release_trust_anchor":
        return _game_builder_import_module(".release_trust_anchor", __name__)
    if module == ".reviewed_knowledge":
        return _game_builder_import_module(".reviewed_knowledge", __name__)
    if module == ".sega_reproducibility":
        return _game_builder_import_module(".sega_reproducibility", __name__)
    if module == ".sms_native_export":
        return _game_builder_import_module(".sms_native_export", __name__)
    if module == ".sms_rom":
        return _game_builder_import_module(".sms_rom", __name__)
    if module == ".spectrum_native_export":
        return _game_builder_import_module(".spectrum_native_export", __name__)
    if module == ".spectrum_tap":
        return _game_builder_import_module(".spectrum_tap", __name__)
    if module == ".studio_execution_plane":
        return _game_builder_import_module(".studio_execution_plane", __name__)
    if module == ".studio_tool_fabric":
        return _game_builder_import_module(".studio_tool_fabric", __name__)
    if module == ".tiled_map_import":
        return _game_builder_import_module(".tiled_map_import", __name__)
    if module == ".vectrex_native_export":
        return _game_builder_import_module(".vectrex_native_export", __name__)
    if module == ".vectrex_rom":
        return _game_builder_import_module(".vectrex_rom", __name__)
    raise ImportError("unregistered lazy export module")



def __getattr__(name: str):
    module = _KNOWLEDGE_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_load_trusted_lazy_module(module), name)
    globals()[name] = value
    return value


__all__ += list(_KNOWLEDGE_EXPORTS)
