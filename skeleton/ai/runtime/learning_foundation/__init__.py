from .lifecycle import (
    LifecycleTransitionReceipt,
    ModelBillOfMaterials,
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
    ModelMigrationDecision,
)
from .multimodal import (
    LearningModality,
    MultimodalCorpus,
    MultimodalFoundationError,
    MultimodalRecord,
    RetrievalHit,
    SpeechChunkReceipt,
    TextProjection,
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
)
"""P3-T2 provider-independent data, training and multimodal runtime."""

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

__all__ = [
    "LifecycleTransitionReceipt",
    "ModelBillOfMaterials",
    "ModelLifecycleError",
    "ModelLifecycleRegistry",
    "ModelLifecycleState",
    "ModelMigrationDecision",
    "LearningModality",
    "MultimodalCorpus",
    "MultimodalFoundationError",
    "MultimodalRecord",
    "RetrievalHit",
    "SpeechChunkReceipt",
    "TextProjection",
    "CurriculumDecision",
    "CurriculumStage",
    "EpisodeReceipt",
    "LearningProgram",
    "LearningProgramError",
    "ReinforcementEnvironment",
    "VerifierCandidate",
    "VerifierDecision",
    "DistributedTrainingPlan",
    "LocalTrainingControlPlane",
    "MetricGate",
    "PostTrainingReceipt",
    "RecoveryReceipt",
    "TrainingCheckpoint",
    "TrainingControlError",
    "TrainingEvaluationDecision",
    "TrainingObservation",
    "TrainingRun",
    "TrainingShard",
    "ContentAddressedStore",
    "DataConflictError",
    "DataPlaneError",
    "DataQualityReport",
    "DatasetRecord",
    "DatasetRegistry",
    "DatasetTransactionReceipt",
    "IngestionRecord",
]


# Preserve stable P3 multimodal evidence and measured-rollout APIs from the
# reconciled source modules without eagerly loading optional runtime backends.
__all__ += ["VerifierEvaluationReceipt", "MigrationParityCase", "ModelMigrationEvaluationReceipt",
            "ModelMigrationReceipt", "ModelMigrationRollbackReceipt", "LifecycleBackupReceipt",
            "ModelLifecyclePersistenceError", "SQLiteModelLifecycleRepository",
            "MultimodalTrainingManifest", "MultimodalTrainingSample"]

_LAZY_EXPORTS = {
    "learning": frozenset({"VerifierEvaluationReceipt"}),
    "lifecycle": frozenset({"MigrationParityCase", "ModelMigrationEvaluationReceipt",
                            "ModelMigrationReceipt", "ModelMigrationRollbackReceipt"}),
    "lifecycle_repository": frozenset({"LifecycleBackupReceipt", "ModelLifecyclePersistenceError",
                                       "SQLiteModelLifecycleRepository"}),
    "multimodal": frozenset({"MultimodalTrainingManifest", "MultimodalTrainingSample"}),
    "content_retrieval": frozenset({
        "ContentSignalIndex", "ContentFeatureReceipt", "ContentSimilarityHit",
    }),
    "rollout": frozenset({
        "MeasuredModelRollout", "MeasuredRolloutError", "RolloutPlan",
        "RolloutGatePolicy", "RolloutMeasurementReceipt", "RolloutStageReceipt",
        "RolloutActionReceipt", "LocalUsageTariff",
    }),
    "temporal": frozenset({
        "LiveSpeechExecution", "SpeechFrameEvidence", "SpeechExecutionReceipt",
        "VideoEvidenceIndex", "TimedMediaFragment", "VideoFragmentEvidence",
        "VideoTimelineReceipt", "VideoFusionHit",
    }),
}


def _load_literal_export_module(owner: str):
    """Resolve only source-declared lazy export owners; never load arbitrary names."""
    from importlib import import_module

    if owner == ".content_retrieval":
        return import_module(".content_retrieval", __name__)
    elif owner == ".learning":
        return import_module(".learning", __name__)
    elif owner == ".lifecycle":
        return import_module(".lifecycle", __name__)
    elif owner == ".lifecycle_repository":
        return import_module(".lifecycle_repository", __name__)
    elif owner == ".multimodal":
        return import_module(".multimodal", __name__)
    elif owner == ".rollout":
        return import_module(".rollout", __name__)
    elif owner == ".temporal":
        return import_module(".temporal", __name__)
    raise ImportError("unregistered lazy export owner: " + repr(owner))


def __getattr__(name: str):
    for module_name, names in _LAZY_EXPORTS.items():
        if name in names:
            from importlib import import_module

            value = getattr(_load_literal_export_module("." + module_name), name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
