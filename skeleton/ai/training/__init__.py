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
}


def __getattr__(name: str):
    module = _GOVERNANCE_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_training_import_module(module, __name__), name)
    globals()[name] = value
    return value


__all__ += list(_GOVERNANCE_EXPORTS)
