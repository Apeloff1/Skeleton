"""Reproducibility receipt pins exactly what data and code initialized weights."""
from __future__ import annotations
from dataclasses import dataclass
import platform
from .factory import GenesisInstance
from .canonical import digest, required_sha
from .errors import refuse


@dataclass(frozen=True, slots=True)
class InitializationStamp:
    exact_git_sha256: str
    runtime_code_sha256: str
    init_policy_sha256: str
    original_source_sha256: str
    vocab_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    checkpoint_sha256: str
    python_version: str

    @property
    def digest(self)->str:
        return digest(self.report())

    def report(self)->dict:
        return {
            "schema":"skeleton.native-genesis.initialization-stamp.v1",
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "actual_sgd_steps":0,
            "quality_verified":False,
            "release_certified":False,
        }


def stamp(instance: GenesisInstance, *,exact_git_sha256:str,
          runtime_code_sha256:str)->InitializationStamp:
    if type(instance) is not GenesisInstance:
        refuse("stamp-genesis-type")
    required_sha(exact_git_sha256,"git")
    required_sha(runtime_code_sha256,"code")
    return InitializationStamp(
        exact_git_sha256,runtime_code_sha256,instance.policy.digest,
        instance.source.source_sha256,instance.vocabulary.digest,
        instance.runtime.model_digest,instance.runtime.tokenizer.digest,
        instance.checkpoint_sha256,platform.python_version(),
    )
