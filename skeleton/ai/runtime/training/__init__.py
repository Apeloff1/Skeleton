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
    "ExecutedCurriculumReceipt",
    "ExecutedEpisodeReceipt",
    "ExecutedEvaluationReceipt",
    "LocalPolicyObservation",
    "LocalPostTrainingPolicy",
    "NeuralLocalTrainer",
    "NeuralTrainingArtifact",
    "PostTrainingExecutionError",
    "PostTrainingExecutionSpec",
    "PostTrainingQualificationReceipt",
    "PostTrainingRunner",
]


def __getattr__(name: str):
    if name in {"NeuralLocalTrainer", "NeuralTrainingArtifact"}:
        from . import neural_trainer

        value = getattr(neural_trainer, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
