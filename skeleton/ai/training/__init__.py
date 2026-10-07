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

from .project_learning import LearningApproval, ProjectLearningError, ProjectOutcome, ProjectTrainingAdmission, admit_project_outcome
from .project_learning_run import ProjectLearningRun, build_project_learning_manifest
from .lifecycle_proof import LifecycleProof, LifecycleProofError, LifecycleStage, prove_project_learning
__all__ += ["LearningApproval","ProjectLearningError","ProjectOutcome","ProjectTrainingAdmission","admit_project_outcome","ProjectLearningRun","build_project_learning_manifest","LifecycleProof","LifecycleProofError","LifecycleStage","prove_project_learning"]

from .promotion_lifecycle import RuntimeAdmission, RollbackProof, extend_with_promotion
__all__ += ["RuntimeAdmission","RollbackProof","extend_with_promotion"]
