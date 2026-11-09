"""Bind shadow acquisition to real candidate training artifacts.

This is the missing custody bridge between an idle Dragon knowledge lease and
a materialized candidate model. It binds source content to a dataset revision,
a candidate-only TrainingManifest and the resulting TrainingCheckpoint. It can
stage the candidate in the persistent shadow ledger, but it cannot admit those
weights for inference without the independent mirror and runtime gates.
"""
from __future__ import annotations

from dataclasses import dataclass

from .flgb_training_runtime import (
    CandidateWeights, DatasetRevision, TrainingCheckpoint, TrainingManifest,
    digest_json, require_digest, require_id,
)
from .shadow_weight_intake import (
    ShadowIntakeLease, ShadowKnowledgeQueue,
)
from .shadow_weight_ledger import ShadowWeightLedger, ShadowWeightSnapshot
from .shadow_weights import ShadowWeightBatch, ShadowWeightError


@dataclass(frozen=True, slots=True)
class ShadowTrainingHandoff:
    knowledge_id: str
    knowledge_digest: str
    dataset_revision_digest: str
    training_manifest_digest: str
    training_checkpoint_digest: str
    candidate_digest: str
    shadow_batch_digest: str

    def __post_init__(self) -> None:
        require_id(self.knowledge_id, "knowledge_id")
        for name in (
            "knowledge_digest", "dataset_revision_digest",
            "training_manifest_digest", "training_checkpoint_digest",
            "candidate_digest", "shadow_batch_digest",
        ):
            require_digest(getattr(self, name), name)

    @property
    def digest(self) -> str:
        return digest_json({
            "knowledge_id": self.knowledge_id,
            "knowledge_digest": self.knowledge_digest,
            "dataset_revision_digest": self.dataset_revision_digest,
            "training_manifest_digest": self.training_manifest_digest,
            "training_checkpoint_digest": self.training_checkpoint_digest,
            "candidate_digest": self.candidate_digest,
            "shadow_batch_digest": self.shadow_batch_digest,
        })


def build_shadow_training_handoff(
    lease: ShadowIntakeLease,
    dataset: DatasetRevision,
    manifest: TrainingManifest,
    checkpoint: TrainingCheckpoint,
    *,
    candidate_id: str,
) -> tuple[ShadowTrainingHandoff, ShadowWeightBatch]:
    """Build the candidate from the checkpoint, never from a claimed score.

    This direct handoff uses precisely one source dataset so an unknown
    additional training source cannot be smuggled into the lineage. Explicit
    multi-dataset training belongs in a separately governed training run.
    """
    if not isinstance(lease, ShadowIntakeLease):
        raise ShadowWeightError("shadow intake lease required")
    if not isinstance(dataset, DatasetRevision):
        raise ShadowWeightError("materialized source dataset revision required")
    if not isinstance(manifest, TrainingManifest):
        raise ShadowWeightError("candidate-only training manifest required")
    if not isinstance(checkpoint, TrainingCheckpoint):
        raise ShadowWeightError("completed training checkpoint required")
    require_id(candidate_id, "candidate_id")
    item = lease.knowledge
    if dataset.content_digest != item.content_digest:
        raise ShadowWeightError("training dataset does not match leased shadow knowledge")
    if manifest.dataset_revision_digests != (dataset.digest,):
        raise ShadowWeightError("training manifest uses other or untracked datasets")
    if manifest.base_model_digest != item.base_model_digest:
        raise ShadowWeightError("training baseline changed after shadow intake")
    if checkpoint.run_manifest_digest != manifest.digest:
        raise ShadowWeightError("training checkpoint does not belong to this run")
    if checkpoint.sequence < 1:
        raise ShadowWeightError("candidate requires a post-training checkpoint")
    candidate = CandidateWeights(
        candidate_id=candidate_id,
        weights_digest=checkpoint.weights_digest,
        training_lineage_digest=checkpoint.digest,
        base_model_digest=manifest.base_model_digest,
    )
    if candidate.weights_digest == candidate.base_model_digest:
        raise ShadowWeightError("training produced no distinct candidate weights")
    batch = ShadowWeightBatch(candidate=candidate, sources=item.sources)
    receipt = ShadowTrainingHandoff(
        knowledge_id=item.knowledge_id,
        knowledge_digest=item.digest,
        dataset_revision_digest=dataset.digest,
        training_manifest_digest=manifest.digest,
        training_checkpoint_digest=checkpoint.digest,
        candidate_digest=candidate.digest,
        shadow_batch_digest=batch.digest,
    )
    return receipt, batch


def stage_trained_shadow(
    queue: ShadowKnowledgeQueue,
    ledger: ShadowWeightLedger,
    lease: ShadowIntakeLease,
    dataset: DatasetRevision,
    manifest: TrainingManifest,
    checkpoint: TrainingCheckpoint,
    *,
    candidate_id: str,
    expected_shadow_revision: int | None = None,
) -> tuple[ShadowTrainingHandoff, ShadowWeightSnapshot]:
    """Commit a trained candidate to shadow custody, then acknowledge intake.

    Stage-first is intentional: if the worker crashes between the two SQLite
    transactions, re-staging the same immutable batch is idempotent. The
    separate acknowledgement fences a stale worker against duplicate work.
    Nothing is promoted or loaded into a serving model in this step.
    """
    if not isinstance(queue, ShadowKnowledgeQueue):
        raise ShadowWeightError("shadow intake queue required")
    if not isinstance(ledger, ShadowWeightLedger):
        raise ShadowWeightError("shadow weight ledger required")
    receipt, batch = build_shadow_training_handoff(
        lease, dataset, manifest, checkpoint, candidate_id=candidate_id,
    )
    # Reserve the candidate in durable intake *before* staging a second ledger.
    # After any crash a newly leased worker must reproduce the same candidate;
    # it cannot replace the reserved weights with another training run.
    queue.reserve_candidate(lease, batch.candidate)
    snapshot = ledger.stage(batch, expected_revision=expected_shadow_revision)
    queue.acknowledge(lease, batch.candidate)
    return receipt, snapshot


__all__ = [
    "ShadowTrainingHandoff", "build_shadow_training_handoff",
    "stage_trained_shadow",
]
