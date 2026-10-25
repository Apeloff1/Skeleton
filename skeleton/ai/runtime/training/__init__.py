"""Native training and model-improvement runtime surfaces."""

from .data import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    LineageReceipt,
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

from .trainer import LocalTrainingArtifact, ReferenceLocalTrainer, corpus_digest
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


# Reconcile the previously implemented P3 training adapters without importing
# optional NumPy/native tooling whenever the training package is imported.
# Attribute access loads only the requested authority-bound adapter.  Keeping
# this out of __all__ preserves lightweight wildcard imports on small devices.
__all__ += ["MaterializedDatasetReceipt", "MaterializedTrainingSource", "SourceAuthorityBinding"]

_LAZY_EXPORTS = {
    "data": frozenset({"MaterializedDatasetReceipt", "MaterializedTrainingSource",
                       "SourceAuthorityBinding"}),
    "learning_pipeline": frozenset({
        "ExecutedCurriculumReceipt", "ExecutedEpisodeReceipt",
        "ExecutedEvaluationReceipt", "LocalPolicyObservation",
        "LocalPostTrainingPolicy", "PostTrainingExecutionError",
        "PostTrainingExecutionSpec", "PostTrainingQualificationReceipt",
        "PostTrainingRunner",
    }),
    "elastic_trainer": frozenset({"ElasticLocalTrainer", "ElasticTrainingArtifact"}),
    "preference_trainer": frozenset({
        "PreferenceLocalTrainer", "PreferencePair", "PreferenceTrainingArtifact",
    }),
    "neural_trainer": frozenset({"NeuralLocalTrainer", "NeuralTrainingArtifact"}),
    "distributed_trainer": frozenset({
        "LocalDataParallelTrainer", "LocalDataParallelArtifact",
    }),
    "observability": frozenset({
        "TrainingObserver", "TrainingObservationReport", "TrainingObservationError",
    }),
    "checkpoint_archive": frozenset({
        "TrainingCheckpointArchive", "CheckpointArchiveReceipt",
        "CheckpointArchiveError", "CheckpointArchiveContents",
    }),
    "verifier": frozenset({
        "EvaluationModelSource", "LocalVerifier", "MeasuredVerifierRunner",
        "MeasuredVerifierReceipt", "MeasuredVerifierQualification",
        "MeasuredVerifierError", "VerifierGatePolicy",
    }),
}


def _load_trusted_lazy_module(module_name: str):
    """Import from the repository-owned export map using only literal targets."""
    if module_name == "checkpoint_archive":
        return import_module(".checkpoint_archive", __name__)
    if module_name == "data":
        return import_module(".data", __name__)
    if module_name == "distributed_trainer":
        return import_module(".distributed_trainer", __name__)
    if module_name == "elastic_trainer":
        return import_module(".elastic_trainer", __name__)
    if module_name == "learning_pipeline":
        return import_module(".learning_pipeline", __name__)
    if module_name == "neural_trainer":
        return import_module(".neural_trainer", __name__)
    if module_name == "observability":
        return import_module(".observability", __name__)
    if module_name == "preference_trainer":
        return import_module(".preference_trainer", __name__)
    if module_name == "verifier":
        return import_module(".verifier", __name__)
    raise ImportError("unregistered lazy export module")



def __getattr__(name: str):
    for module_name, names in _LAZY_EXPORTS.items():
        if name in names:
            from importlib import import_module

            value = getattr(_load_trusted_lazy_module(module_name), name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
