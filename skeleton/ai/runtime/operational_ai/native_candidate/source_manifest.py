"""Canonical source inventory receipt for the 576 original training records."""
from __future__ import annotations
from dataclasses import dataclass

from .catalog import iter_examples, verify_exact
from .rights import verify_rights
from .dedup import require_unique
from .splits import partition
from .errors import deny


@dataclass(frozen=True, slots=True)
class SourceManifest:
    source_sha256: str
    rights_sha256: str
    partition_sha256: str
    dedup_sha256: str
    example_count: int

    def record(self) -> dict:
        return {
            "schema": "skeleton.native-candidate.source-manifest.v1",
            "source_sha256": self.source_sha256,
            "rights_sha256": self.rights_sha256,
            "partition_sha256": self.partition_sha256,
            "dedup_sha256": self.dedup_sha256,
            "example_count": self.example_count,
            "source_kind": "original-synthetic",
            "training_permitted_scope": "offline_native_candidate_training",
            "model_trained": False, "release_certified": False,
        }


def generate() -> SourceManifest:
    examples = tuple(iter_examples())
    if not verify_exact(examples):
        deny("source-manifest-incomplete")
    rights = verify_rights(examples)
    dedup = require_unique(examples)
    split = partition(examples)
    return SourceManifest(
        rights.source_hash, rights.rights_digest, split.digest,
        dedup["dedup_sha256"], len(examples),
    )
