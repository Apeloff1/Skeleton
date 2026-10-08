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
}


def __getattr__(name: str):
    module = _GOVERNANCE_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_training_import_module(module, __name__), name)
    globals()[name] = value
    return value


__all__ += list(_GOVERNANCE_EXPORTS)
