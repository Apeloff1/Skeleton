from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from skeleton.ai.game_builder.evaluator_provenance import (
    EvaluatorProvenanceBindingError,
    evaluator_provenance_from_canonical_execution,
    gate_result_from_canonical_execution,
    judge_verdict_from_canonical_execution,
)
from skeleton.ai.game_builder.contracts import QUALITY_AXES
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


EVIDENCE = "evaluation-evidence-" + "e" * 32


def _request(
    *,
    execution_id: str = "execution:evaluator:001",
) -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id="operation:evaluate-game-candidate",
        execution_id=execution_id,
        objective="Independently evaluate a governed game-builder candidate.",
        context_policy={"blind": True},
        tool_policy={"allow": ["simulator"]},
        resource_budget={"tokens": 1000},
        stop_policy={"mode": "complete"},
        created_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
    )


def _finalization(
    *,
    execution_id: str = "execution:evaluator:001",
    status: str = "completed",
) -> ExecutionFinalizationIntent:
    return ExecutionFinalizationIntent(
        result=AIExecutionResult(
            operation_id="operation:evaluate-game-candidate",
            execution_id=execution_id,
            status=status,
            usage={"tokens": 200},
            completed_at=datetime(2026, 10, 7, 0, 2, tzinfo=timezone.utc),
            final_output="evaluation complete" if status == "completed" else None,
            provider_receipts=("provider-receipt:evaluator:001",),
            evidence_refs=(EVIDENCE,),
        ),
        expected_execution_version=2,
        staged_at=datetime(2026, 10, 7, 0, 2, tzinfo=timezone.utc),
    )


def _model() -> ModelArtifactManifest:
    representation = RepresentationSpec(
        tokenizer_family="byte-bpe",
        tokenizer_version="1",
        vocabulary_digest=_sha("eval-vocab"),
        normalization_spec="NFC",
        byte_fallback_policy="lossless",
        special_token_map={"<bos>": 1, "<eos>": 2},
        bos_token="<bos>",
        eos_token="<eos>",
    )
    return ModelArtifactManifest(
        model_id="independent-evaluator-model",
        architecture_id="decoder-v1",
        architecture_config_digest=_sha("eval-architecture"),
        representation=representation,
        weight_shards=(
            WeightShard("weights/evaluator.safetensors", _sha("eval-weights"), 4096),
        ),
        weight_format="safetensors",
        dtype="bf16",
        quantization="none",
        model_code_digest=_sha("eval-model-code"),
        runtime_abi="skeleton.inference.v1",
        data_manifest_root=_sha("eval-data"),
        eval_evidence_root=_sha("eval-evidence-root"),
        provenance_root=_sha("eval-provenance"),
    )


def test_canonical_evaluator_provenance_binds_execution_and_model_identity() -> None:
    request = _request()
    finalization = _finalization()
    model = _model()
    provenance = evaluator_provenance_from_canonical_execution(
        evaluator_id="judge-1",
        method_id="simulator",
        request=request,
        finalization=finalization,
        model_manifest=model,
        source_revision="a" * 40,
    )

    assert provenance.evaluator_id == "judge-1"
    assert provenance.authority_kind == "ai_execution"
    assert provenance.execution_identity_digest == request.identity_digest
    assert provenance.finalization_intent_digest == finalization.intent_digest
    assert provenance.authority_identity_digest == model.artifact_id.split(":", 1)[1]
    assert provenance.output_evidence_refs == (EVIDENCE,)
    assert len(provenance.digest) == 64


def test_canonical_gate_factory_requires_execution_committed_evidence() -> None:
    gate = gate_result_from_canonical_execution(
        gate_id="rights",
        passed=True,
        evidence_digest=EVIDENCE,
        evaluator_id="judge-rights",
        method_id="rights-audit",
        request=_request(),
        finalization=_finalization(),
        model_manifest=_model(),
        source_revision="b" * 40,
    )
    assert gate.evidence_digest == EVIDENCE
    assert len(gate.evidence_binding_digest) == 64

    with pytest.raises(
        ValueError,
        match="gate evidence must be referenced by evaluator execution output",
    ):
        gate_result_from_canonical_execution(
            gate_id="rights",
            passed=True,
            evidence_digest="substituted-evidence-" + "s" * 32,
            evaluator_id="judge-rights",
            method_id="rights-audit",
            request=_request(),
            finalization=_finalization(),
            model_manifest=_model(),
            source_revision="b" * 40,
        )


def test_canonical_judge_factory_binds_verdict_to_execution_evidence() -> None:
    verdict = judge_verdict_from_canonical_execution(
        evaluator_id="judge-panel-1",
        candidate_digest="candidate-" + "c" * 64,
        quality={axis: 0.6 for axis in QUALITY_AXES},
        confidence=0.9,
        evidence_digest=EVIDENCE,
        method_id="simulator",
        request=_request(),
        finalization=_finalization(),
        model_manifest=_model(),
        source_revision="c" * 40,
    )
    assert verdict.evaluator_provenance.evaluator_id == verdict.evaluator_id
    assert verdict.evidence_digest == EVIDENCE
    assert len(verdict.evidence_binding_digest) == 64
    assert len(verdict.digest) == 64


def test_canonical_evaluator_bridge_rejects_execution_substitution() -> None:
    with pytest.raises(
        EvaluatorProvenanceBindingError,
        match="execution_id does not match",
    ):
        evaluator_provenance_from_canonical_execution(
            evaluator_id="judge-1",
            method_id="simulator",
            request=_request(),
            finalization=_finalization(execution_id="execution:evaluator:substituted"),
            model_manifest=_model(),
            source_revision="d" * 40,
        )


def test_canonical_evaluator_bridge_rejects_noncompleted_execution() -> None:
    with pytest.raises(
        EvaluatorProvenanceBindingError,
        match="completed AI execution",
    ):
        evaluator_provenance_from_canonical_execution(
            evaluator_id="judge-1",
            method_id="simulator",
            request=_request(),
            finalization=_finalization(status="failed"),
            model_manifest=_model(),
            source_revision="d" * 40,
        )
