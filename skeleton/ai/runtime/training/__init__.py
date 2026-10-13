"""Native training and model-improvement runtime surfaces."""

from .data import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    LineageReceipt,
    MaterializedDatasetReceipt,
    MaterializedTrainingSource,
    SourceAuthorityBinding,
    SyntheticDataReceipt,
)

__all__ = [
    "DataQualityReport",
    "DataQualityRule",
    "DatasetManifest",
    "DatasetRegistry",
    "DatasetSplit",
    "IngestEnvelope",
    "LineageReceipt",
    "MaterializedDatasetReceipt",
    "MaterializedTrainingSource",
    "SourceAuthorityBinding",
    "SyntheticDataReceipt",
]

from .control import (
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
    WorkerLease,
)

__all__ += [
    "TrainingCheckpoint",
    "TrainingRepository",
    "TrainingRunManifest",
    "TrainingStateError",
    "TrainingTelemetry",
    "WorkerLease",
]

from .evaluation import (
    CandidateQualification,
    EvaluationCase,
    EvaluationHarness,
    EvaluationLedger,
    EvaluationResult,
    EvaluationSuite,
    TrainingEvaluationGate,
    VerifierReport,
)
from .trainer import LocalTrainingArtifact, ReferenceLocalTrainer, corpus_digest

__all__ += [
    "CandidateQualification",
    "EvaluationCase",
    "EvaluationHarness",
    "EvaluationLedger",
    "EvaluationResult",
    "EvaluationSuite",
    "LocalTrainingArtifact",
    "ReferenceLocalTrainer",
    "TrainingEvaluationGate",
    "VerifierReport",
    "corpus_digest",
]

from .post_training import (
    CurriculumDecision,
    CurriculumEngine,
    CurriculumStage,
    DeterministicRLEnvironment,
    PostTrainingExperiment,
    PostTrainingLedger,
    RLEnvironmentSpec,
    RLStepReceipt,
)

__all__ += [
    "CurriculumDecision",
    "CurriculumEngine",
    "CurriculumStage",
    "DeterministicRLEnvironment",
    "PostTrainingExperiment",
    "PostTrainingLedger",
    "RLEnvironmentSpec",
    "RLStepReceipt",
]

from .learning_pipeline import (
    ExecutedCurriculumReceipt,
    ExecutedEpisodeReceipt,
    ExecutedEvaluationReceipt,
    LocalPolicyObservation,
    LocalPostTrainingPolicy,
    PostTrainingExecutionError,
    PostTrainingExecutionSpec,
    PostTrainingQualificationReceipt,
    PostTrainingRunner,
)

__all__ += [
    "CheckpointArchiveContents",
    "CheckpointArchiveError",
    "CheckpointArchiveReceipt",
    "ElasticLocalTrainer",
    "ElasticTrainingArtifact",
    "EvaluationModelSource",
    "ExecutedCurriculumReceipt",
    "ExecutedEpisodeReceipt",
    "ExecutedEvaluationReceipt",
    "LocalDataParallelArtifact",
    "LocalDataParallelTrainer",
    "LocalPolicyObservation",
    "LocalPostTrainingPolicy",
    "LocalVerifier",
    "MeasuredVerifierError",
    "MeasuredVerifierQualification",
    "MeasuredVerifierReceipt",
    "MeasuredVerifierRunner",
    "NeuralLocalTrainer",
    "NeuralTrainingArtifact",
    "PostTrainingExecutionError",
    "PostTrainingExecutionSpec",
    "PostTrainingQualificationReceipt",
    "PostTrainingRunner",
    "PreferenceLocalTrainer",
    "PreferencePair",
    "PreferenceTrainingArtifact",
    "TrainingCheckpointArchive",
    "TrainingObservationError",
    "TrainingObservationReport",
    "TrainingObserver",
    "VerifierGatePolicy",
]


def __getattr__(name: str):
    for module_name, names in (
        ("elastic_trainer", {"ElasticLocalTrainer", "ElasticTrainingArtifact"}),
        ("preference_trainer", {"PreferenceLocalTrainer", "PreferencePair", "PreferenceTrainingArtifact"}),
        ("observability", {"TrainingObserver", "TrainingObservationReport", "TrainingObservationError"}),
    ):
        if name in names:
            import importlib

            value = getattr(importlib.import_module("." + module_name, __name__), name)
            globals()[name] = value
            return value
    if name in {
        "TrainingCheckpointArchive",
        "CheckpointArchiveReceipt",
        "CheckpointArchiveError",
        "CheckpointArchiveContents",
    }:
        from . import checkpoint_archive

        value = getattr(checkpoint_archive, name)
        globals()[name] = value
        return value
    if name in {
        "EvaluationModelSource",
        "LocalVerifier",
        "MeasuredVerifierRunner",
        "MeasuredVerifierReceipt",
        "MeasuredVerifierQualification",
        "MeasuredVerifierError",
        "VerifierGatePolicy",
    }:
        from . import verifier

        value = getattr(verifier, name)
        globals()[name] = value
        return value
    if name in {"LocalDataParallelTrainer", "LocalDataParallelArtifact"}:
        from . import distributed_trainer

        value = getattr(distributed_trainer, name)
        globals()[name] = value
        return value
    if name in {"NeuralLocalTrainer", "NeuralTrainingArtifact"}:
        from . import neural_trainer

        value = getattr(neural_trainer, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
