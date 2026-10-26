"""Provider-neutral FLGB-02 model-runtime and native execution contracts.

Optional serving, persistence and native-transformer implementations load only
when their exported names are requested. The base package must stay usable by
standard-library-only contract clients without pydantic, Torch or a database.
"""
from __future__ import annotations

from importlib import import_module

# Keep all public contract names available without importing optional runtimes.
_LAZY_EXPORTS = {
    "ALLOWED_TRANSITIONS": ".flgb_model_runtime",
    "BatchGenerationRequest": ".runtime_contracts",
    "BatchRequest": ".flgb_model_runtime",
    "ChatMessage": ".chat_protocol",
    "ChatTranscript": ".chat_protocol",
    "ChatTurnResult": ".chat_engine",
    "ConversationStore": ".conversation_store",
    "DeviceDescriptor": ".flgb_model_runtime",
    "DevicePolicy": ".runtime_contracts",
    "DeviceReceipt": ".runtime_contracts",
    "DurableConversationCoordinator": ".conversation_persistence",
    "GenerationConfig": ".runtime_contracts",
    "KVCacheEntry": ".flgb_model_runtime",
    "LocalModelReceipt": ".flgb_model_runtime",
    "LocalModelRequest": ".flgb_model_runtime",
    "ModelIdentity": ".flgb_model_runtime",
    "ModelLifecycle": ".flgb_model_runtime",
    "ModelRegistry": ".flgb_model_runtime",
    "ModelRuntimeError": ".flgb_model_runtime",
    "NativeChatEngine": ".chat_engine",
    "NativeChatWorkspace": ".chat_workspace",
    "NativeConversationService": ".conversation_service",
    "NativeConversationSession": ".native_llm_runtime",
    "PersistenceBinding": ".conversation_persistence",
    "Placement": ".flgb_model_runtime",
    "plan_continuous_batches": ".flgb_model_runtime",
    "plan_device_placement": ".flgb_model_runtime",
    "plan_kv_admission": ".flgb_model_runtime",
    "QuantizationProfile": ".flgb_model_runtime",
    "ReplayMismatch": ".runtime_contracts",
    "ReplayReceipt": ".runtime_contracts",
    "Replica": ".flgb_model_runtime",
    "route_request": ".flgb_model_runtime",
    "RuntimeArchitecture": ".runtime_contracts",
    "RuntimeContractError": ".runtime_contracts",
    "RuntimeEvent": ".runtime_contracts",
    "RuntimeLimits": ".runtime_contracts",
    "RuntimeUsage": ".runtime_contracts",
    "ServingReceipt": ".conversation_service",
    "SessionRecord": ".conversation_service",
    "SpeculativeReceipt": ".flgb_model_runtime",
    "StoredConversation": ".conversation_store",
    "TokenSequence": ".flgb_model_runtime",
    "VocabularyManifest": ".flgb_model_runtime",
    "WeightLoadPlan": ".flgb_model_runtime",
    "WeightShard": ".flgb_model_runtime",
    "NativeActivationReceipt": ".weight_activation",
    "NativeRollbackReceipt": ".weight_activation",
    "NativeWeightDeployment": ".weight_activation",
    "WeightShardStoreError": ".weight_shard_store",
    "WeightShardStore": ".weight_shard_store",
    "WeightGatewayError": ".weight_gateway",
    "PinnedWeightRequest": ".weight_gateway",
    "NativeWeightGateway": ".weight_gateway",
    "WorkspaceEvent": ".chat_workspace",
    "WorkspaceRecord": ".chat_workspace",
    "BatchGenerationResult": ".native_llm_runtime",
    "GenerationResult": ".native_llm_runtime",
    "GenerationStream": ".native_llm_runtime",
    "InferenceResult": ".native_llm_runtime",
    "NativeLLMRuntime": ".native_llm_runtime",
    "CancellationToken": ".runtime_service",
    "NativeModelService": ".runtime_service",
    "NativeServiceError": ".runtime_service",
    "NativeServiceResult": ".runtime_service",
    "NativeTokenizer": ".tokenization",
    "StreamingTextFeed": ".tokenization",
    "TokenBatch": ".tokenization",
    "TokenWindow": ".tokenization",
    "TokenizerContractError": ".tokenization",
    "TokenizerLimits": ".tokenization",
    "batch_token_windows": ".tokenization",
    "deserialize_token_sequence": ".tokenization",
    "iter_context_windows": ".tokenization",
    "serialize_token_sequence": ".tokenization",
    "validate_model_snapshot": ".runtime_checkpoint",
    "restore_admission_scheduler": ".admission_checkpoint",
    "AuthenticatedFileCheckpointReplica": ".admission_redundancy",
    "CheckpointReplica": ".admission_redundancy",
    "FileCheckpointReplica": ".admission_redundancy",
    "ReplicationReceipt": ".admission_redundancy",
    "RedundantRecovery": ".admission_redundancy",
    "publish_redundant_checkpoint": ".admission_redundancy",
    "recover_redundant_checkpoint": ".admission_redundancy",
    "repair_redundant_checkpoint": ".admission_redundancy",
    "AdmissionDecision": ".admission_scheduler",
    "AdmissionLimits": ".admission_scheduler",
    "RuntimeAdmissionScheduler": ".admission_scheduler",
    "ScheduledRequest": ".admission_scheduler",
    "InferencePhase": ".iteration_scheduler",
    "IterationPlan": ".iteration_scheduler",
    "IterationScheduler": ".iteration_scheduler",
    "IterationSlice": ".iteration_scheduler",
    "IterationWork": ".iteration_scheduler",
    "DEFAULT_RUNTIME_EPOCHS": ".runtime_epochs",
    "EpochStatus": ".runtime_epochs",
    "RuntimeEpoch": ".runtime_epochs",
    "RuntimeEpochRegistry": ".runtime_epochs",
    "DEFAULT_RUNTIME_POLICY_COMPILER": ".runtime_policy",
    "RuntimePolicy": ".runtime_policy",
    "RuntimePolicyCompiler": ".runtime_policy",
    "DEFAULT_RUNTIME_SIGNALS": ".runtime_signals",
    "RuntimeSignal": ".runtime_signals",
    "RuntimeSignalRegistry": ".runtime_signals",
    "SignalMaturity": ".runtime_signals",
    "RequestTelemetry": ".serving_telemetry",
    "ServingTelemetryWindow": ".serving_telemetry",
    "ResourcePlan": ".slo_planner",
    "RuntimeEstimate": ".slo_planner",
    "SLOResourcePlanner": ".slo_planner",
    "SLOTarget": ".slo_planner",
    "DEFAULT_TEMPORAL_RUNTIME_POLICY_COMPILER": ".temporal_policy",
    "TemporalRuntimePolicy": ".temporal_policy",
    "TemporalRuntimePolicyCompiler": ".temporal_policy",
    "PolicyAwareServingPlanner": ".serving_policy",
    "ServiceClass": ".serving_policy",
    "ServingPlan": ".serving_policy",
    "ServingRequest": ".serving_policy",
    "DeterministicRuntimeEstimator": ".runtime_feedback",
    "FeedbackLimits": ".runtime_feedback",
    "FeedbackReceipt": ".runtime_feedback",
    "ClosedLoopServingController": ".closed_loop_serving",
    "ControlDecision": ".closed_loop_serving",
    "ExecutionTiming": ".execution_telemetry",
    "CausalTrainingBatch": ".text_pipeline",
    "CorpusTrainingReceipt": ".text_pipeline",
    "DecadeCorpusBucket": ".text_pipeline",
    "DecadeCoverageReceipt": ".text_pipeline",
    "DecadeSamplingPlan": ".text_pipeline",
    "DecadeSignalVector": ".text_pipeline",
    "DecadeTrainingSignal": ".text_pipeline",
    "GovernedTrainingInput": ".text_pipeline",
    "ModelInputBatch": ".text_pipeline",
    "PipelineReplayCheckpoint": ".text_pipeline",
    "PreparedCorpus": ".text_pipeline",
    "PreparedText": ".text_pipeline",
    "RoundTripReceipt": ".text_pipeline",
    "PromotionAuthorizationRequest": ".text_pipeline",
    "SourceProvenanceGraph": ".text_pipeline",
    "SourceProvenanceNode": ".text_pipeline",
    "SupervisedTextExample": ".text_pipeline",
    "TemporalContradiction": ".text_pipeline",
    "TemporalEvaluationGate": ".text_pipeline",
    "TemporalEvaluationResult": ".text_pipeline",
    "TemporalEvaluationSlice": ".text_pipeline",
    "TemporalRetrievalCandidate": ".text_pipeline",
    "TemporalRetrievalPlan": ".text_pipeline",
    "TemporalRetentionResult": ".text_pipeline",
    "TemporalRetentionGate": ".text_pipeline",
    "TemporalRetentionTrajectory": ".text_pipeline",
    "TemporalConflictCluster": ".text_pipeline",
    "TemporalEvidence": ".text_pipeline",
    "TemporalSourceEvidence": ".text_pipeline",
    "TemporalSupersession": ".text_pipeline",
    "WalkForwardSnapshot": ".text_pipeline",
    "TemporalTrainingSignal": ".text_pipeline",
    "TemporalInstant": ".text_pipeline",
    "TemporalInterval": ".text_pipeline",
    "TextPipelineConfig": ".text_pipeline",
    "TextTokenPipeline": ".text_pipeline",
    "TrainingInputReceipt": ".text_pipeline",
    "deserialize_causal_training_batch": ".text_pipeline",
    "arbitrate_temporal_evidence": ".text_pipeline",
    "decade_weight_ppm": ".text_pipeline",
    "independent_confidence_ppm": ".text_pipeline",
    "provenance_independence_group": ".text_pipeline",
    "source_evidence_from_provenance": ".text_pipeline",
    "walk_forward_snapshot": ".text_pipeline",
    "deserialize_model_input_batch": ".text_pipeline",
    "mask_causal_prefix": ".text_pipeline",
    "materialize_causal_training_batch": ".text_pipeline",
    "materialize_model_batch": ".text_pipeline",
    "serialize_causal_training_batch": ".text_pipeline",
    "serialize_model_input_batch": ".text_pipeline",
    "normalize_text": ".text_normalization",
    "RuntimePromotionError": ".training_admission",
    "AdmissionLedger": ".training_admission",
    "admit_candidate_model": ".training_admission",
    "execute_rollback": ".training_admission",
}


def _load_trusted_lazy_module(module_name: str):
    """Import from the repository-owned export map using only literal targets."""
    if module_name == ".admission_checkpoint":
        return import_module(".admission_checkpoint", __name__)
    if module_name == ".admission_redundancy":
        return import_module(".admission_redundancy", __name__)
    if module_name == ".admission_scheduler":
        return import_module(".admission_scheduler", __name__)
    if module_name == ".chat_engine":
        return import_module(".chat_engine", __name__)
    if module_name == ".chat_protocol":
        return import_module(".chat_protocol", __name__)
    if module_name == ".chat_workspace":
        return import_module(".chat_workspace", __name__)
    if module_name == ".closed_loop_serving":
        return import_module(".closed_loop_serving", __name__)
    if module_name == ".conversation_persistence":
        return import_module(".conversation_persistence", __name__)
    if module_name == ".conversation_service":
        return import_module(".conversation_service", __name__)
    if module_name == ".conversation_store":
        return import_module(".conversation_store", __name__)
    if module_name == ".execution_telemetry":
        return import_module(".execution_telemetry", __name__)
    if module_name == ".flgb_model_runtime":
        return import_module(".flgb_model_runtime", __name__)
    if module_name == ".iteration_scheduler":
        return import_module(".iteration_scheduler", __name__)
    if module_name == ".native_llm_runtime":
        return import_module(".native_llm_runtime", __name__)
    if module_name == ".runtime_checkpoint":
        return import_module(".runtime_checkpoint", __name__)
    if module_name == ".runtime_contracts":
        return import_module(".runtime_contracts", __name__)
    if module_name == ".runtime_epochs":
        return import_module(".runtime_epochs", __name__)
    if module_name == ".runtime_feedback":
        return import_module(".runtime_feedback", __name__)
    if module_name == ".runtime_policy":
        return import_module(".runtime_policy", __name__)
    if module_name == ".runtime_service":
        return import_module(".runtime_service", __name__)
    if module_name == ".runtime_signals":
        return import_module(".runtime_signals", __name__)
    if module_name == ".serving_policy":
        return import_module(".serving_policy", __name__)
    if module_name == ".serving_telemetry":
        return import_module(".serving_telemetry", __name__)
    if module_name == ".slo_planner":
        return import_module(".slo_planner", __name__)
    if module_name == ".temporal_policy":
        return import_module(".temporal_policy", __name__)
    if module_name == ".text_normalization":
        return import_module(".text_normalization", __name__)
    if module_name == ".text_pipeline":
        return import_module(".text_pipeline", __name__)
    if module_name == ".tokenization":
        return import_module(".tokenization", __name__)
    if module_name == ".training_admission":
        return import_module(".training_admission", __name__)
    if module_name == ".weight_activation":
        return import_module(".weight_activation", __name__)
    if module_name == ".weight_gateway":
        return import_module(".weight_gateway", __name__)
    if module_name == ".weight_shard_store":
        return import_module(".weight_shard_store", __name__)
    raise ImportError("unregistered lazy export module")



def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_load_trusted_lazy_module(module_name), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))

__all__ = [
    "RuntimePromotionError",
    "AdmissionLedger",
    "admit_candidate_model",
    "execute_rollback",
    "CausalTrainingBatch",
    "CorpusTrainingReceipt",
    "DecadeCorpusBucket",
    "DecadeCoverageReceipt",
    "DecadeSamplingPlan",
    "DecadeSignalVector",
    "DecadeTrainingSignal",
    "GovernedTrainingInput",
    "ModelInputBatch",
    "PipelineReplayCheckpoint",
    "PreparedCorpus",
    "PreparedText",
    "RoundTripReceipt",
    "PromotionAuthorizationRequest",
    "SourceProvenanceGraph",
    "SourceProvenanceNode",
    "SupervisedTextExample",
    "TemporalContradiction",
    "TemporalEvaluationGate",
    "TemporalEvaluationResult",
    "TemporalEvaluationSlice",
    "TemporalRetrievalCandidate",
    "TemporalRetrievalPlan",
    "TemporalRetentionResult",
    "TemporalRetentionGate",
    "TemporalRetentionTrajectory",
    "TemporalConflictCluster",
    "TemporalEvidence",
    "TemporalSourceEvidence",
    "TemporalSupersession",
    "WalkForwardSnapshot",
    "TemporalTrainingSignal",
    "TemporalInstant",
    "TemporalInterval",
    "TextPipelineConfig",
    "TextTokenPipeline",
    "TrainingInputReceipt",
    "deserialize_causal_training_batch",
    "arbitrate_temporal_evidence",
    "decade_weight_ppm",
    "independent_confidence_ppm",
    "provenance_independence_group",
    "source_evidence_from_provenance",
    "walk_forward_snapshot",
    "deserialize_model_input_batch",
    "mask_causal_prefix",
    "materialize_causal_training_batch",
    "materialize_model_batch",
    "serialize_causal_training_batch",
    "serialize_model_input_batch",
    "normalize_text",
    "PolicyAwareServingPlanner",
    "ServiceClass",
    "ServingPlan",
    "ServingRequest",
    "DeterministicRuntimeEstimator",
    "FeedbackLimits",
    "FeedbackReceipt",
    "ClosedLoopServingController",
    "ControlDecision",
    "ExecutionTiming",
    "restore_admission_scheduler",
    "AuthenticatedFileCheckpointReplica",
    "CheckpointReplica",
    "FileCheckpointReplica",
    "ReplicationReceipt",
    "RedundantRecovery",
    "publish_redundant_checkpoint",
    "recover_redundant_checkpoint",
    "repair_redundant_checkpoint",
    "AdmissionDecision",
    "AdmissionLimits",
    "RuntimeAdmissionScheduler",
    "ScheduledRequest",
    "InferencePhase",
    "IterationPlan",
    "IterationScheduler",
    "IterationSlice",
    "IterationWork",
    "DEFAULT_RUNTIME_EPOCHS",
    "EpochStatus",
    "RuntimeEpoch",
    "RuntimeEpochRegistry",
    "DEFAULT_RUNTIME_POLICY_COMPILER",
    "RuntimePolicy",
    "RuntimePolicyCompiler",
    "DEFAULT_RUNTIME_SIGNALS",
    "RuntimeSignal",
    "RuntimeSignalRegistry",
    "SignalMaturity",
    "RequestTelemetry",
    "ServingTelemetryWindow",
    "ResourcePlan",
    "RuntimeEstimate",
    "SLOResourcePlanner",
    "SLOTarget",
    "DEFAULT_TEMPORAL_RUNTIME_POLICY_COMPILER",
    "TemporalRuntimePolicy",
    "TemporalRuntimePolicyCompiler",
    "ALLOWED_TRANSITIONS",
    "AdmissionDecision",
    "AdmissionLimits",
    "BatchGenerationRequest",
    "BatchGenerationResult",
    "CancellationToken",
    "BatchRequest",
    "ClosedLoopServingController",
    "ControlDecision",
    "DEFAULT_RUNTIME_EPOCHS",
    "DEFAULT_RUNTIME_POLICY_COMPILER",
    "DEFAULT_TEMPORAL_RUNTIME_POLICY_COMPILER",
    "DEFAULT_RUNTIME_SIGNALS",
    "DeterministicRuntimeEstimator",
    "DeviceDescriptor",
    "DevicePolicy",
    "DeviceReceipt",
    "EpochStatus",
    "ExecutionTiming",
    "FeedbackLimits",
    "FeedbackReceipt",
    "GenerationConfig",
    "GenerationResult",
    "GenerationStream",
    "InferenceResult",
    "InferencePhase",
    "IterationPlan",
    "IterationScheduler",
    "IterationSlice",
    "IterationWork",
    "KVCacheEntry",
    "LocalModelReceipt",
    "LocalModelRequest",
    "ModelIdentity",
    "ModelLifecycle",
    "ModelRegistry",
    "ModelRuntimeError",
    "NativeLLMRuntime",
    "NativeConversationSession",
    "NativeConversationService",
    "NativeChatWorkspace",
    "WorkspaceRecord",
    "WorkspaceEvent",
    "NativeChatEngine",
    "ChatTurnResult",
    "ChatMessage",
    "ChatTranscript",
    "ConversationStore",
    "DurableConversationCoordinator",
    "PersistenceBinding",
    "StoredConversation",
    "SessionRecord",
    "ServingReceipt",
    "NativeModelService",
    "NativeServiceError",
    "NativeServiceResult",
    "NativeTokenizer",
    "Placement",
    "PolicyAwareServingPlanner",
    "QuantizationProfile",
    "ReplayMismatch",
    "ReplayReceipt",
    "Replica",
    "RuntimeAdmissionScheduler",
    "RuntimeEpoch",
    "RuntimeEpochRegistry",
    "RequestTelemetry",
    "ResourcePlan",
    "RuntimeEstimate",
    "RuntimePolicy",
    "RuntimePolicyCompiler",
    "RuntimeSignal",
    "RuntimeSignalRegistry",
    "RuntimeArchitecture",
    "RuntimeContractError",
    "RuntimeEvent",
    "RuntimeLimits",
    "RuntimeUsage",
    "SLOResourcePlanner",
    "SLOTarget",
    "ScheduledRequest",
    "ServiceClass",
    "ServingPlan",
    "ServingRequest",
    "ServingTelemetryWindow",
    "SignalMaturity",
    "SpeculativeReceipt",
    "StreamingTextFeed",
    "TemporalRuntimePolicy",
    "TemporalRuntimePolicyCompiler",
    "TokenBatch",
    "TokenSequence",
    "TokenWindow",
    "TokenizerContractError",
    "TokenizerLimits",
    "VocabularyManifest",
    "WeightLoadPlan",
    "WeightShard",
    "batch_token_windows",
    "deserialize_token_sequence",
    "iter_context_windows",
    "plan_continuous_batches",
    "plan_device_placement",
    "plan_kv_admission",
    "route_request",
    "serialize_token_sequence",
    "validate_model_snapshot",
]
