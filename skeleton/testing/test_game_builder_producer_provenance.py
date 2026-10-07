from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from skeleton.ai.game_builder.producer_provenance import (
    ProducerProvenanceBindingError,
    producer_provenance_from_canonical_execution,
)
from skeleton.ai.learning.model_identity import (
    ModelArtifactManifest,
    RepresentationSpec,
    WeightShard,
)
from skeleton.ai.runtime.contracts.ai_execution import (
    AIExecutionRequest,
    AIExecutionResult,
    ExecutionFinalizationIntent,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request() -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id="operation:game-builder",
        execution_id="execution:game-builder:001",
        objective="Produce one governed game-builder candidate.",
        context_policy={"mode": "project"},
        tool_policy={"allow": []},
        resource_budget={"tokens": 1000},
        stop_policy={"mode": "complete"},
        created_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
    )


def _finalization(
    *,
    execution_id: str = "execution:game-builder:001",
    status: str = "completed",
) -> ExecutionFinalizationIntent:
    return ExecutionFinalizationIntent(
        result=AIExecutionResult(
            operation_id="operation:game-builder",
            execution_id=execution_id,
            status=status,
            usage={"tokens": 100},
            completed_at=datetime(2026, 10, 7, 0, 1, tzinfo=timezone.utc),
            final_output="candidate" if status == "completed" else None,
            provider_receipts=("provider-receipt:001",),
            evidence_refs=("evidence:001",),
            artifact_refs=("artifact:001",),
        ),
        expected_execution_version=3,
        staged_at=datetime(2026, 10, 7, 0, 1, tzinfo=timezone.utc),
    )


def _model() -> ModelArtifactManifest:
    representation = RepresentationSpec(
        tokenizer_family="byte-bpe",
        tokenizer_version="1",
        vocabulary_digest=_sha("vocab"),
        normalization_spec="NFC",
        byte_fallback_policy="lossless",
        special_token_map={"<bos>": 1, "<eos>": 2},
        bos_token="<bos>",
        eos_token="<eos>",
    )
    return ModelArtifactManifest(
        model_id="game-builder-model",
        architecture_id="decoder-v1",
        architecture_config_digest=_sha("architecture"),
        representation=representation,
        weight_shards=(
            WeightShard("weights/model.safetensors", _sha("weights"), 4096),
        ),
        weight_format="safetensors",
        dtype="bf16",
        quantization="none",
        model_code_digest=_sha("model-code"),
        runtime_abi="skeleton.inference.v1",
        data_manifest_root=_sha("data"),
        eval_evidence_root=_sha("eval"),
        provenance_root=_sha("provenance"),
    )


def test_canonical_execution_derives_replayable_candidate_provenance() -> None:
    request = _request()
    finalization = _finalization()
    model = _model()

    provenance = producer_provenance_from_canonical_execution(
        project_id="project:alpha",
        run_id="run:forge-001",
        request=request,
        finalization=finalization,
        model_manifest=model,
        producer_behavior_digest=_sha("behavior-bundle"),
        source_revision="a" * 40,
    )

    assert provenance.operation_id == request.operation_id
    assert provenance.execution_id == request.execution_id
    assert provenance.execution_identity_digest == request.identity_digest
    assert provenance.finalization_intent_digest == finalization.intent_digest
    assert provenance.model_identity_digest == model.artifact_id.split(":", 1)[1]
    assert provenance.provider_receipt_refs == ("provider-receipt:001",)
    assert len(provenance.digest) == 64


def test_canonical_execution_rejects_execution_identity_substitution() -> None:
    with pytest.raises(
        ProducerProvenanceBindingError,
        match="execution_id does not match",
    ):
        producer_provenance_from_canonical_execution(
            project_id="project:alpha",
            run_id="run:forge-001",
            request=_request(),
            finalization=_finalization(execution_id="execution:substituted"),
            model_manifest=_model(),
            producer_behavior_digest=_sha("behavior-bundle"),
            source_revision="a" * 40,
        )


def test_canonical_execution_rejects_noncompleted_result() -> None:
    with pytest.raises(
        ProducerProvenanceBindingError,
        match="completed AI execution",
    ):
        producer_provenance_from_canonical_execution(
            project_id="project:alpha",
            run_id="run:forge-001",
            request=_request(),
            finalization=_finalization(status="failed"),
            model_manifest=_model(),
            producer_behavior_digest=_sha("behavior-bundle"),
            source_revision="a" * 40,
        )
