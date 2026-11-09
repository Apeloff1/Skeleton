"""Verified bridge from canonical AI execution/model contracts into game-builder provenance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .contracts import ArtifactIdentity, Candidate, ProducerProvenance


class ProducerProvenanceBindingError(ValueError):
    """Canonical execution/model identities cannot be bound safely."""


def producer_provenance_from_canonical_execution(
    *,
    project_id: str,
    run_id: str,
    request: object,
    finalization: object,
    model_manifest: object,
    producer_behavior_digest: str,
    source_revision: str,
) -> ProducerProvenance:
    """Derive candidate provenance from canonical, self-verifying upstream contracts.

    Imports are intentionally local so the deterministic game-builder contracts do
    not acquire provider/runtime execution behavior at import time.
    """

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
        raise ProducerProvenanceBindingError(
            "candidate provenance requires a completed AI execution result"
        )
    if result.operation_id != request.operation_id:
        raise ProducerProvenanceBindingError(
            "final execution operation_id does not match execution request"
        )
    if result.execution_id != request.execution_id:
        raise ProducerProvenanceBindingError(
            "final execution execution_id does not match execution request"
        )

    artifact_id = model_manifest.artifact_id
    if (
        not isinstance(artifact_id, str)
        or not artifact_id.startswith("model:")
        or len(artifact_id) != len("model:") + 64
    ):
        raise ProducerProvenanceBindingError(
            "model artifact identity is not canonical"
        )
    model_identity_digest = artifact_id.split(":", 1)[1]

    return ProducerProvenance(
        project_id=project_id,
        run_id=run_id,
        operation_id=request.operation_id,
        execution_id=request.execution_id,
        execution_identity_digest=request.identity_digest,
        finalization_intent_digest=finalization.intent_digest,
        model_identity_digest=model_identity_digest,
        producer_behavior_digest=producer_behavior_digest,
        source_revision=source_revision,
        provider_receipt_refs=tuple(result.provider_receipts),
        output_artifact_refs=tuple(result.artifact_refs),
        output_evidence_refs=tuple(result.evidence_refs),
    )


def candidate_from_canonical_execution(
    *,
    producer_id: str,
    project_id: str,
    run_id: str,
    request: object,
    finalization: object,
    model_manifest: object,
    producer_behavior_digest: str,
    source_revision: str,
    artifact: ArtifactIdentity,
    quality: Mapping[str, float],
    evidence_digests: Iterable[str],
    assumption_digest: str,
    parent_candidate_digests: Iterable[str] = (),
) -> Candidate:
    """Construct a candidate only when its payload is committed by the execution."""

    provenance = producer_provenance_from_canonical_execution(
        project_id=project_id,
        run_id=run_id,
        request=request,
        finalization=finalization,
        model_manifest=model_manifest,
        producer_behavior_digest=producer_behavior_digest,
        source_revision=source_revision,
    )
    return Candidate.create(
        producer_id=producer_id,
        producer_provenance=provenance,
        artifact=artifact,
        quality=quality,
        evidence_digests=evidence_digests,
        assumption_digest=assumption_digest,
        parent_candidate_digests=parent_candidate_digests,
    )


__all__ = [
    "ProducerProvenanceBindingError",
    "candidate_from_canonical_execution",
    "producer_provenance_from_canonical_execution",
]
