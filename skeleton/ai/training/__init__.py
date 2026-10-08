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

from .native_transformer import (
    GovernedTrainingDataset,
    NativeTrainingError,
    NativeTrainingReceipt,
    NativeTransformerTrainingConfig,
    TRAINING_SCHEMA as NATIVE_TRANSFORMER_TRAINING_SCHEMA,
    TRAINING_SCOPE as NATIVE_TRANSFORMER_TRAINING_SCOPE,
    corpus_digest,
    governed_dataset,
    normalization_digest,
    normalize_documents,
    train_native_transformer_candidate,
)

__all__ += [
    "GovernedTrainingDataset",
    "NativeTrainingError",
    "NativeTrainingReceipt",
    "NativeTransformerTrainingConfig",
    "NATIVE_TRANSFORMER_TRAINING_SCHEMA",
    "NATIVE_TRANSFORMER_TRAINING_SCOPE",
    "corpus_digest",
    "governed_dataset",
    "normalization_digest",
    "normalize_documents",
    "train_native_transformer_candidate",
]
