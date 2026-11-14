"""Stable code-independent original source manifest for model and challenge provenance."""
from __future__ import annotations
from dataclasses import dataclass
from .source import prepare_source
from .challenge_catalog import inventory
from .challenge_overlap import scan
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class SourceManifest:
    training_sha256:str
    rights_sha256:str
    partition_sha256:str
    evaluation_sha256:str
    evaluation_cases:int
    overlap_proof_sha256:str

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.source-manifest.v1",
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "evaluation_excluded_from_optimizer":True,
            "evaluation_excluded_from_vocabulary":True,
            "weights_created":False,"release_certified":False,
        }


def generate()->SourceManifest:
    training=prepare_source()
    challenges=inventory()
    contamination=scan()
    if not contamination["exact_clear"]:
        reject("manifest-contamination")
    if challenges["count"]!=768:
        reject("manifest-incomplete-evaluation")
    return SourceManifest(
        training.corpus_sha256,training.rights_sha256,
        training.partition_sha256,challenges["source_sha256"],
        challenges["count"],digest(contamination),
    )
