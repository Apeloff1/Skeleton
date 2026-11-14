"""Integrate the exact original, rights-scoped candidate source with SFT."""
from __future__ import annotations
from dataclasses import dataclass
from ..native_candidate.catalog import iter_examples,verify_exact
from ..native_candidate.splits import partition,Partition
from ..native_candidate.rights import verify_rights
from ..native_candidate.dedup import require_unique
from ..native_candidate.semantic_oracle import verify_all
from ..native_candidate.contamination import scan,require_clear_exact
from .errors import reject


@dataclass(frozen=True,slots=True)
class SourceScope:
    groups:Partition
    corpus_sha256:str
    rights_sha256:str
    partition_sha256:str
    train_count:int
    validation_count:int
    holdout_count:int

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.source.v1",
            "corpus_sha256":self.corpus_sha256,
            "rights_sha256":self.rights_sha256,
            "partition_sha256":self.partition_sha256,
            "train_count":self.train_count,
            "validation_count":self.validation_count,
            "holdout_count":self.holdout_count,
            "training_scope":"offline_native_candidate_training",
            "train_only":True,"weights_created":False,
            "release_certified":False,
        }


def prepare_source()->SourceScope:
    items=tuple(iter_examples())
    if len(items)!=576 or not verify_exact(items):
        reject("source-incomplete")
    require_unique(items)
    truth=verify_all(items)
    if not truth["all_correct"]:
        reject("source-truth")
    rights=verify_rights(items)
    if rights.allowed_scope!="offline_native_candidate_training":
        reject("source-purpose")
    overlap=scan(items)
    require_clear_exact(overlap)
    groups=partition(items)
    if tuple(map(len,(groups.train,groups.validation,groups.holdout)))!=(432,72,72):
        reject("source-splits")
    return SourceScope(
        groups,rights.source_hash,rights.rights_digest,groups.digest,
        432,72,72,
    )
