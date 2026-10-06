"""Canonical evaluator-execution bridges for game-builder authority evidence."""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import EvaluatorProvenance, GateResult
from .evaluation import JudgeVerdict


class EvaluatorProvenanceBindingError(ValueError):
    """Canonical evaluator execution cannot be bound safely."""


def evaluator_provenance_from_canonical_execution(
    *,
    evaluator_id: str,
    method_id: str,
    request: object,
    finalization: object,
    model_manifest: object,
    source_revision: str,
) -> EvaluatorProvenance:
    """Derive independent evaluator identity from canonical execution contracts."""

    from skeleton.ai.learning.model_identity import ModelArtifactManifest
    from skeleton.ai.runtime.contracts.ai_execution import (
        AIExecutionRequest,
        ExecutionFinalizationIntent,
    )

    if not isinstance(request, AIExecutionRequest):
        raise TypeError("request must be AIExecutionRequest")
    if not isinstance(finalization, ExecutionFinalizationIntent):
        raise TypeError("finalization must be ExecutionFinalizationIntent")
    if not isinstance(model_manifest, ModelArtifactManifest):
        raise TypeError("model_manifest must be ModelArtifactManifest")

    result = finalization.result
    if result.status != "completed":
        raise EvaluatorProvenanceBindingError(
            "evaluator provenance requires a completed AI execution result"
        )
    if result.operation_id != request.operation_id:
        raise EvaluatorProvenanceBindingError(
            "evaluator final operation_id does not match execution request"
        )
    if result.execution_id != request.execution_id:
        raise EvaluatorProvenanceBindingError(
            "evaluator final execution_id does not match execution request"
        )

    artifact_id = model_manifest.artifact_id
    if (
        not isinstance(artifact_id, str)
        or not artifact_id.startswith("model:")
        or len(artifact_id) != len("model:") + 64
    ):
        raise EvaluatorProvenanceBindingError(
            "evaluator model artifact identity is not canonical"
        )

    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=request.operation_id,
        execution_id=request.execution_id,
        execution_identity_digest=request.identity_digest,
        finalization_intent_digest=finalization.intent_digest,
        model_identity_digest=artifact_id.split(":", 1)[1],
        method_id=method_id,
        source_revision=source_revision,
        provider_receipt_refs=tuple(result.provider_receipts),
        output_evidence_refs=tuple(result.evidence_refs),
    )


def gate_result_from_canonical_execution(
    *,
    gate_id: str,
    passed: bool,
    evidence_digest: str,
    evaluator_id: str,
    method_id: str,
    request: object,
    finalization: object,
    model_manifest: object,
    source_revision: str,
    non_compensable: bool = True,
) -> GateResult:
    provenance = evaluator_provenance_from_canonical_execution(
        evaluator_id=evaluator_id,
        method_id=method_id,
        request=request,
        finalization=finalization,
        model_manifest=model_manifest,
        source_revision=source_revision,
    )
    return GateResult(
        gate_id=gate_id,
        passed=passed,
        evidence_digest=evidence_digest,
        evaluator_provenance=provenance,
        non_compensable=non_compensable,
    )


def judge_verdict_from_canonical_execution(
    *,
    evaluator_id: str,
    candidate_digest: str,
    quality: Mapping[str, float],
    confidence: float,
    evidence_digest: str,
    method_id: str,
    request: object,
    finalization: object,
    model_manifest: object,
    source_revision: str,
) -> JudgeVerdict:
    provenance = evaluator_provenance_from_canonical_execution(
        evaluator_id=evaluator_id,
        method_id=method_id,
        request=request,
        finalization=finalization,
        model_manifest=model_manifest,
        source_revision=source_revision,
    )
    return JudgeVerdict.create(
        evaluator_id=evaluator_id,
        evaluator_provenance=provenance,
        candidate_digest=candidate_digest,
        quality=quality,
        confidence=confidence,
        evidence_digest=evidence_digest,
        method_id=method_id,
    )


__all__ = [
    "EvaluatorProvenanceBindingError",
    "evaluator_provenance_from_canonical_execution",
    "gate_result_from_canonical_execution",
    "judge_verdict_from_canonical_execution",
]
