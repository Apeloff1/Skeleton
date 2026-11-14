"""Pinned source/model/tokenizer/training-code context; no unsupported portability claims."""
from __future__ import annotations
from dataclasses import dataclass
from platform import python_version,system,machine
from .canonical import digest,require_sha
from .errors import reject


@dataclass(frozen=True,slots=True)
class ExecutionStamp:
    git_sha256:str
    operator_declared_code_sha256:str
    model_sha256:str
    tokenizer_sha256:str
    source_sha256:str
    challenges_sha256:str
    python:str
    platform:str
    cpu_arch:str

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.execution-stamp.v1",
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "source_code_sha_verified_independently":False,
            "cross_platform_weights_identical":False,
            "hardware_qualified":False,
        }

    @property
    def sha256(self)->str:
        return digest(self.record())


def stamp(*,git_sha256:str,code_sha256:str,model_sha256:str,
          tokenizer_sha256:str,source_sha256:str,challenges_sha256:str)->ExecutionStamp:
    for name,val in (
        ("git",git_sha256),("code",code_sha256),("model",model_sha256),
        ("tokenizer",tokenizer_sha256),("source",source_sha256),
        ("challenges",challenges_sha256),
    ):
        require_sha(val,name)
    return ExecutionStamp(
        git_sha256,code_sha256,model_sha256,tokenizer_sha256,
        source_sha256,challenges_sha256,python_version(),
        system().lower(),machine().lower(),
    )
