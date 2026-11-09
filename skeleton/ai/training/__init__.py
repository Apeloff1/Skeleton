"""Governed FLGB-07 training and candidate-weight contracts."""
from .flgb_training_runtime import (
    AdapterTrainingRun, CandidateWeights, ContaminationFinding, DatasetRevision,
    DatasetRights, DedupRecord, DistillationRun, MirrorEvaluation,
    PromotionEvidence, TrainingCheckpoint, TrainingContractError,
    TrainingManifest, deduplicate, scan_contamination,
)
from .post_training import (
    PostTrainingCandidate, PostTrainingError, PostTrainingRun, PreferenceDataset,
)
__all__=[
    "AdapterTrainingRun","CandidateWeights","ContaminationFinding","DatasetRevision",
    "DatasetRights","DedupRecord","DistillationRun","MirrorEvaluation",
    "PromotionEvidence","TrainingCheckpoint","TrainingContractError",
    "TrainingManifest","deduplicate","scan_contamination","PostTrainingCandidate",
    "PostTrainingError","PostTrainingRun","PreferenceDataset",
]

from .project_learning import (
    LearningApproval, ProjectLearningError, ProjectOutcome,
    ProjectTrainingAdmission, admit_project_outcome,
)
__all__ += [
    "LearningApproval", "ProjectLearningError", "ProjectOutcome",
    "ProjectTrainingAdmission", "admit_project_outcome",
]

from .project_learning_run import ProjectLearningRun, build_project_learning_manifest
__all__ += ["ProjectLearningRun", "build_project_learning_manifest"]


# Lazy governance exports keep the candidate training baseline lightweight.
from importlib import import_module as _training_import_module

_GOVERNANCE_EXPORTS = {
    "ImprovementDirection": ".shadow_candidate_gate",
    "ImprovementAxis": ".shadow_candidate_gate",
    "ImprovementMatrix": ".shadow_candidate_gate",
    "CandidateReleaseProposal": ".shadow_candidate_gate",
    "prepare_candidate_release": ".shadow_candidate_gate",
    "ReleaseJournalError": ".model_release_journal",
    "ReleaseState": ".model_release_journal",
    "ExternalReleaseReceipt": ".model_release_journal",
    "ReleaseStatus": ".model_release_journal",
    "ModelReleaseJournal": ".model_release_journal",
    "ShadowWeightError": ".shadow_weight_pipeline",
    "ShadowState": ".shadow_weight_pipeline",
    "SourceAttestation": ".shadow_weight_pipeline",
    "ShadowWeightIntake": ".shadow_weight_pipeline",
    "ShadowPolicy": ".shadow_weight_pipeline",
    "ShadowReview": ".shadow_weight_pipeline",
    "ShadowRecord": ".shadow_weight_pipeline",
    "ShadowEvent": ".shadow_weight_pipeline",
    "ShadowWeightPipeline": ".shadow_weight_pipeline",
    "DurableShadowWeightPipeline": ".shadow_weight_store",
    "TemporalFact": ".temporal_facts",
    "TemporalSnapshot": ".temporal_facts",
    "snapshot_facts": ".temporal_facts",
    "require_historical_snapshot": ".temporal_facts",
    "TemporalQuery": ".temporal_retrieval",
    "TemporalRetrievalReceipt": ".temporal_retrieval",
    "TemporalEvidenceQualification": ".temporal_retrieval",
    "retrieve_temporal_facts": ".temporal_retrieval",
    "qualify_temporal_retrieval": ".temporal_retrieval",
    "ForecastObservation": ".temporal_drift",
    "CalibrationReceipt": ".temporal_drift",
    "DriftWindow": ".temporal_drift",
    "ChangePointState": ".temporal_drift",
    "score_calibration": ".temporal_drift",
    "adaptive_drift_window": ".temporal_drift",
    "update_change_point_state": ".temporal_drift",
    "require_calibrated_forecaster": ".temporal_drift",
    "TemporalResearchAuthority": ".temporal_research_authority",
    "authorize_research_temporal_plane": ".temporal_research_authority",
    "LifecycleProofError": ".lifecycle_proof",
    "LifecycleStage": ".lifecycle_proof",
    "LifecycleProof": ".lifecycle_proof",
    "prove_project_learning": ".lifecycle_proof",
    "RuntimeAdmission": ".promotion_lifecycle",
    "RollbackProof": ".promotion_lifecycle",
    "extend_with_promotion": ".promotion_lifecycle",
    "TemporalSignalError": ".temporal_signals",
    "YearSignal": ".temporal_signals",
    "EraBoundary": ".temporal_signals",
    "DecadePolicy": ".temporal_signals",
    "SignalAssessment": ".temporal_signals",
    "DecadeAssessment": ".temporal_signals",
    "decade_of": ".temporal_signals",
    "assess_year_signals": ".temporal_signals",
    "assess_decade_signals": ".temporal_signals",
    "TemporalConsensus": ".temporal_signals",
    "reconcile_temporal_scales": ".temporal_signals",
    "require_consensus_authority": ".temporal_signals",
    "require_signal_authority": ".temporal_signals",
    "BitemporalFact": ".bitemporal_authority",
    "BitemporalSnapshot": ".bitemporal_authority",
    "bitemporal_snapshot": ".bitemporal_authority",
    "require_no_future_knowledge": ".bitemporal_authority",
    "FactVersion": ".temporal_freshness",
    "FreshnessResolution": ".temporal_freshness",
    "resolve_fact_versions": ".temporal_freshness",
    "ProvenanceNode": ".temporal_provenance",
    "IndependenceReceipt": ".temporal_provenance",
    "assess_source_independence": ".temporal_provenance",
    "require_independent_roots": ".temporal_provenance",
    "TemporalCustodyEntry": ".temporal_custody",
    "TemporalCustodyChain": ".temporal_custody",
    "build_custody_chain": ".temporal_custody",
    "append_custody": ".temporal_custody",
    "TemporalRevocation": ".temporal_revocation",
    "RevocationRegistry": ".temporal_revocation",
    "quarantine": ".temporal_quarantine",
    "resolve_quarantine": ".temporal_quarantine",
    "require_learning_release": ".temporal_quarantine",
    "TemporalAuthorityEntry": ".temporal_replay",
    "TemporalAuthorityLedger": ".temporal_replay",
    "TemporalCompetence": ".temporal_benchmark",
    "TemporalBenchmarkReceipt": ".temporal_benchmark",
    "evaluate_temporal_competence": ".temporal_benchmark",
    "require_temporal_benchmark": ".temporal_benchmark",
    "RegimeObservation": ".temporal_invariants",
    "InvarianceReceipt": ".temporal_invariants",
    "assess_regime_invariance": ".temporal_invariants",
    "require_regime_invariance": ".temporal_invariants",
    "ResidualObservation": ".temporal_uncertainty",
    "TemporalUncertaintyReceipt": ".temporal_uncertainty",
    "rolling_uncertainty_set": ".temporal_uncertainty",
    "require_bounded_uncertainty": ".temporal_uncertainty",
    "TemporalEvent": ".temporal_causality",
    "CausalEdge": ".temporal_causality",
    "CausalChronologyReceipt": ".temporal_causality",
    "validate_causal_chronology": ".temporal_causality",
    "TemporalDecision": ".temporal_abstention",
    "decide_temporal_authority": ".temporal_abstention",
    "require_temporal_authorization": ".temporal_abstention",
    "TemporalConsistencyProof": ".temporal_consistency",
    "prove_temporal_consistency": ".temporal_consistency",
    "DecadeProfile": ".temporal_intelligence",
    "DecadeTransition": ".temporal_intelligence",
    "TemporalTrend": ".temporal_intelligence",
    "TemporalAuthorityReceipt": ".temporal_intelligence",
    "build_decade_profiles": ".temporal_intelligence",
    "build_decade_transitions": ".temporal_intelligence",
    "analyze_temporal_trend": ".temporal_intelligence",
    "authorize_temporal_evidence": ".temporal_intelligence",
    "DriftDetectorVote": ".temporal_ensemble",
    "DriftEnsembleReceipt": ".temporal_ensemble",
    "combine_drift_votes": ".temporal_ensemble",
    "require_stable_drift_ensemble": ".temporal_ensemble",
    "TemporalDecisionCertificate": ".temporal_certificate",
    "issue_temporal_certificate": ".temporal_certificate",
    "CertificateRegistration": ".temporal_certificate_registry",
    "CertificateRegistry": ".temporal_certificate_registry",
    "LearningTemporalPolicy": ".temporal_learning_control",
    "TemporalLearningDecision": ".temporal_learning_control",
    "decide_learning_disposition": ".temporal_learning_control",
    "require_weight_eligibility": ".temporal_learning_control",
    "TemporalTrainingAdmission": ".temporal_admission",
    "admit_temporal_training": ".temporal_admission",
    "TemporalPromotionBinding": ".temporal_promotion",
    "bind_temporal_promotion": ".temporal_promotion",
    "require_temporal_promotion": ".temporal_promotion",
    "TemporalBudget": ".temporal_budget",
    "enforce_signal_budget": ".temporal_budget",
    "enforce_fact_budget": ".temporal_budget",
    "CounterfactualBranch": ".temporal_counterfactual",
    "CounterfactualOutcome": ".temporal_counterfactual",
    "require_observed_evidence_not_counterfactual": ".temporal_counterfactual",
    "validate_counterfactual_outcome": ".temporal_counterfactual",
    "TemporalEdit": ".temporal_editing",
    "RippleConstraint": ".temporal_editing",
    "TemporalEditReceipt": ".temporal_editing",
    "validate_temporal_edit": ".temporal_editing",
    "YearInterval": ".temporal_intervals",
    "ShadowWeightError": ".shadow_weights",
    "SourceAttestation": ".shadow_weights",
    "ShadowWeightPolicy": ".shadow_weights",
    "ShadowAssessment": ".shadow_weights",
    "ShadowWeightBatch": ".shadow_weights",
    "ShadowPromotionPermit": ".shadow_weights",
    "authorize_shadow_promotion": ".shadow_weights",
    "independent_evidence_roots": ".shadow_weights",
    "ShadowWeightLedger": ".shadow_weight_ledger",
    "ShadowWeightSnapshot": ".shadow_weight_ledger",
    "ShadowKnowledge": ".shadow_weight_intake",
    "ShadowIntakePolicy": ".shadow_weight_intake",
    "ShadowIntakeAssessment": ".shadow_weight_intake",
    "ShadowIntakeLease": ".shadow_weight_intake",
    "ShadowKnowledgeQueue": ".shadow_weight_intake",
    "assess_shadow_intake": ".shadow_weight_intake",
    "ShadowTrainingHandoff": ".shadow_training_handoff",
    "build_shadow_training_handoff": ".shadow_training_handoff",
    "stage_trained_shadow": ".shadow_training_handoff",

    "ShadowTrainingPaused": ".shadow_idle_training",
    "ShadowTrainingRejected": ".shadow_idle_training",
    "ShadowTrainingArtifacts": ".shadow_idle_training",
    "ShadowWorkReceipt": ".shadow_idle_training",
    "ShadowLeaseSession": ".shadow_idle_training",
    "ShadowIdleTrainingWorker": ".shadow_idle_training",
    "ShadowNativeTrainingPolicy": ".shadow_native_trainer",
    "ShadowNativeTrainer": ".shadow_native_trainer",
    "require_temporal_compatibility": ".temporal_intervals",
}


def _load_trusted_lazy_module(module: str):
    """Import from the repository-owned export map using only literal targets."""
    if module == ".bitemporal_authority":
        return _training_import_module(".bitemporal_authority", __name__)
    if module == ".lifecycle_proof":
        return _training_import_module(".lifecycle_proof", __name__)
    if module == ".model_release_journal":
        return _training_import_module(".model_release_journal", __name__)
    if module == ".promotion_lifecycle":
        return _training_import_module(".promotion_lifecycle", __name__)
    if module == ".shadow_candidate_gate":
        return _training_import_module(".shadow_candidate_gate", __name__)
    if module == ".shadow_idle_training":
        return _training_import_module(".shadow_idle_training", __name__)
    if module == ".shadow_native_trainer":
        return _training_import_module(".shadow_native_trainer", __name__)
    if module == ".shadow_training_handoff":
        return _training_import_module(".shadow_training_handoff", __name__)
    if module == ".shadow_weight_intake":
        return _training_import_module(".shadow_weight_intake", __name__)
    if module == ".shadow_weight_ledger":
        return _training_import_module(".shadow_weight_ledger", __name__)
    if module == ".shadow_weight_pipeline":
        return _training_import_module(".shadow_weight_pipeline", __name__)
    if module == ".shadow_weight_store":
        return _training_import_module(".shadow_weight_store", __name__)
    if module == ".shadow_weights":
        return _training_import_module(".shadow_weights", __name__)
    if module == ".temporal_abstention":
        return _training_import_module(".temporal_abstention", __name__)
    if module == ".temporal_admission":
        return _training_import_module(".temporal_admission", __name__)
    if module == ".temporal_benchmark":
        return _training_import_module(".temporal_benchmark", __name__)
    if module == ".temporal_budget":
        return _training_import_module(".temporal_budget", __name__)
    if module == ".temporal_causality":
        return _training_import_module(".temporal_causality", __name__)
    if module == ".temporal_certificate":
        return _training_import_module(".temporal_certificate", __name__)
    if module == ".temporal_certificate_registry":
        return _training_import_module(".temporal_certificate_registry", __name__)
    if module == ".temporal_consistency":
        return _training_import_module(".temporal_consistency", __name__)
    if module == ".temporal_counterfactual":
        return _training_import_module(".temporal_counterfactual", __name__)
    if module == ".temporal_custody":
        return _training_import_module(".temporal_custody", __name__)
    if module == ".temporal_drift":
        return _training_import_module(".temporal_drift", __name__)
    if module == ".temporal_editing":
        return _training_import_module(".temporal_editing", __name__)
    if module == ".temporal_ensemble":
        return _training_import_module(".temporal_ensemble", __name__)
    if module == ".temporal_facts":
        return _training_import_module(".temporal_facts", __name__)
    if module == ".temporal_freshness":
        return _training_import_module(".temporal_freshness", __name__)
    if module == ".temporal_intelligence":
        return _training_import_module(".temporal_intelligence", __name__)
    if module == ".temporal_intervals":
        return _training_import_module(".temporal_intervals", __name__)
    if module == ".temporal_invariants":
        return _training_import_module(".temporal_invariants", __name__)
    if module == ".temporal_learning_control":
        return _training_import_module(".temporal_learning_control", __name__)
    if module == ".temporal_promotion":
        return _training_import_module(".temporal_promotion", __name__)
    if module == ".temporal_provenance":
        return _training_import_module(".temporal_provenance", __name__)
    if module == ".temporal_quarantine":
        return _training_import_module(".temporal_quarantine", __name__)
    if module == ".temporal_replay":
        return _training_import_module(".temporal_replay", __name__)
    if module == ".temporal_research_authority":
        return _training_import_module(".temporal_research_authority", __name__)
    if module == ".temporal_retrieval":
        return _training_import_module(".temporal_retrieval", __name__)
    if module == ".temporal_revocation":
        return _training_import_module(".temporal_revocation", __name__)
    if module == ".temporal_signals":
        return _training_import_module(".temporal_signals", __name__)
    if module == ".temporal_uncertainty":
        return _training_import_module(".temporal_uncertainty", __name__)
    raise ImportError("unregistered lazy export module")



def __getattr__(name: str):
    module = _GOVERNANCE_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_load_trusted_lazy_module(module), name)
    globals()[name] = value
    return value


__all__ += list(_GOVERNANCE_EXPORTS)
