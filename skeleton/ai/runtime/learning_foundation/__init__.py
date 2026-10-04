"""P3-T2 provider-independent data, training and multimodal runtime."""

from .data import (
    ContentAddressedStore,
    DataConflictError,
    DataPlaneError,
    DataQualityReport,
    DatasetRecord,
    DatasetRegistry,
    DatasetTransactionReceipt,
    IngestionRecord,
)
from .learning import (
    CurriculumDecision,
    CurriculumStage,
    EpisodeReceipt,
    LearningProgram,
    LearningProgramError,
    ReinforcementEnvironment,
    VerifierCandidate,
    VerifierDecision,
    VerifierEvaluationReceipt,
)
from .lifecycle import (
    LifecycleTransitionReceipt,
    MigrationParityCase,
    ModelBillOfMaterials,
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
    ModelMigrationDecision,
    ModelMigrationEvaluationReceipt,
    ModelMigrationReceipt,
    ModelMigrationRollbackReceipt,
)
from .lifecycle_repository import (
    LifecycleBackupReceipt,
    ModelLifecyclePersistenceError,
    SQLiteModelLifecycleRepository,
)
from .multimodal import (
    LearningModality,
    MultimodalCorpus,
    MultimodalFoundationError,
    MultimodalRecord,
    MultimodalTrainingManifest,
    MultimodalTrainingSample,
    RetrievalHit,
    SpeechChunkReceipt,
    TextProjection,
)
from .training import (
    DistributedTrainingPlan,
    LocalTrainingControlPlane,
    MetricGate,
    PostTrainingReceipt,
    RecoveryReceipt,
    TrainingCheckpoint,
    TrainingControlError,
    TrainingEvaluationDecision,
    TrainingObservation,
    TrainingRun,
    TrainingShard,
)

__all__ = [
    "ContentAddressedStore",
    "CurriculumDecision",
    "CurriculumStage",
    "DataConflictError",
    "DataPlaneError",
    "DataQualityReport",
    "DatasetRecord",
    "DatasetRegistry",
    "DatasetTransactionReceipt",
    "DistributedTrainingPlan",
    "EpisodeReceipt",
    "IngestionRecord",
    "LearningModality",
    "LearningProgram",
    "LearningProgramError",
    "LifecycleBackupReceipt",
    "LifecycleTransitionReceipt",
    "LiveSpeechExecution",
    "LocalTrainingControlPlane",
    "MetricGate",
    "MigrationParityCase",
    "ModelBillOfMaterials",
    "ModelLifecycleError",
    "ModelLifecyclePersistenceError",
    "ModelLifecycleRegistry",
    "ModelLifecycleState",
    "ModelMigrationDecision",
    "ModelMigrationEvaluationReceipt",
    "ModelMigrationReceipt",
    "ModelMigrationRollbackReceipt",
    "MultimodalCorpus",
    "MultimodalFoundationError",
    "MultimodalRecord",
    "MultimodalTrainingManifest",
    "MultimodalTrainingSample",
    "PostTrainingReceipt",
    "RecoveryReceipt",
    "ReinforcementEnvironment",
    "RetrievalHit",
    "SQLiteModelLifecycleRepository",
    "SpeechChunkReceipt",
    "SpeechExecutionReceipt",
    "SpeechFrameEvidence",
    "TextProjection",
    "TimedMediaFragment",
    "TrainingCheckpoint",
    "TrainingControlError",
    "TrainingEvaluationDecision",
    "TrainingObservation",
    "TrainingRun",
    "TrainingShard",
    "VerifierCandidate",
    "VerifierDecision",
    "VerifierEvaluationReceipt",
    "VideoEvidenceIndex",
    "VideoFragmentEvidence",
    "VideoFusionHit",
    "VideoTimelineReceipt",
]


def __getattr__(name: str):
    if name in {
        "LiveSpeechExecution",
        "SpeechFrameEvidence",
        "SpeechExecutionReceipt",
        "VideoEvidenceIndex",
        "TimedMediaFragment",
        "VideoFragmentEvidence",
        "VideoTimelineReceipt",
        "VideoFusionHit",
    }:
        from . import temporal

        value = getattr(temporal, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
