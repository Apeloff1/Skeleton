"""Content-addressed native genesis manifest; declares random initialization."""
from __future__ import annotations
from dataclasses import dataclass, fields
from .canonical import digest, bytes_sha, required_sha
from .errors import refuse
from .factory import GenesisInstance

SCHEMA = "skeleton.native-genesis.manifest.v1"


@dataclass(frozen=True, slots=True)
class GenesisManifest:
    policy_sha256: str
    source_sha256: str
    rights_sha256: str
    partition_sha256: str
    vocabulary_sha256: str
    tokenizer_sha256: str
    model_sha256: str
    checkpoint_sha256: str
    initial_optimizer_steps: int = 0
    original_source_only: bool = True
    candidate_only: bool = True

    def __post_init__(self) -> None:
        for field in fields(self):
            if field.name.endswith("sha256"):
                required_sha(getattr(self, field.name), field.name)
        if (self.initial_optimizer_steps != 0 or self.original_source_only is not True
                or self.candidate_only is not True):
            refuse("genesis-manifest-scope")

    def record(self) -> dict:
        return {
            "schema": SCHEMA,
            **{field.name: getattr(self, field.name) for field in fields(self)},
            "weights_trained": False,
            "serving_admitted": False,
            "release_certified": False,
        }

    @property
    def digest(self) -> str:
        return digest(self.record())


def from_instance(genesis: GenesisInstance) -> GenesisManifest:
    if type(genesis) is not GenesisInstance:
        refuse("genesis-instance-required")
    if bytes_sha(genesis.checkpoint) != genesis.checkpoint_sha256:
        refuse("genesis-checkpoint-integrity")
    return GenesisManifest(
        genesis.policy.digest, genesis.source.source_sha256,
        genesis.source.rights_sha256, genesis.source.partitions_sha256,
        genesis.vocabulary.digest, genesis.runtime.tokenizer.digest,
        genesis.runtime.model_digest, genesis.checkpoint_sha256,
    )
