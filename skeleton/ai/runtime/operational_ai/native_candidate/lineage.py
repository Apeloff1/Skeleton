"""Bind FLGB training lineage to exact original, approved candidate corpus."""
from __future__ import annotations
from dataclasses import dataclass

from skeleton.ai.training.flgb_training_runtime import DatasetRevision, TrainingManifest
from .rights import RightsProof
from .plan import TrainingPlan
from .splits import Partition
from .strict import digest
from .errors import deny


@dataclass(frozen=True, slots=True)
class TrainingLineage:
    dataset: DatasetRevision
    manifest: TrainingManifest
    rights: RightsProof
    train_count: int
    validation_count: int
    holdout_count: int
    partition_digest: str

    def record(self) -> dict:
        return {
            "dataset_digest": self.dataset.digest,
            "training_manifest_digest": self.manifest.digest,
            "rights_digest": self.rights.rights_digest,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "holdout_count": self.holdout_count,
            "partition_digest": self.partition_digest,
            "output_kind": self.manifest.output_kind,
        }


def bind_lineage(
    plan: TrainingPlan, part: Partition, rights: RightsProof, *,
    code_digest: str, optimizer_steps: int,
) -> TrainingLineage:
    from .strict import sha
    sha(code_digest, "training-code")
    if type(plan) is not TrainingPlan or type(part) is not Partition:
        deny("lineage-types")
    if type(rights) is not RightsProof:
        deny("lineage-rights")
    if rights.records != 576 or len(part.train) != 432:
        deny("lineage-partition")
    dataset = DatasetRevision(
        dataset_id=rights.dataset_id,
        revision=0, content_digest=rights.source_hash,
        rights_digest=rights.rights_digest,
        transform_digest=digest({"render": "instruction-response-v1",
                                 "partitions": part.digest}),
    )
    manifest = TrainingManifest(
        run_id=plan.run_id, base_model_digest=plan.expected_base_model_sha256,
        dataset_revision_digests=(dataset.digest,),
        code_digest=code_digest,
        config_digest=plan.digest,
        seed_manifest_digest=digest({
            "curriculum": part.digest,
            "data": rights.source_hash, "seed": 0,
        }),
        max_steps=optimizer_steps,
        output_kind="candidate-only",
    )
    return TrainingLineage(dataset, manifest, rights, len(part.train),
                           len(part.validation), len(part.holdout), part.digest)
