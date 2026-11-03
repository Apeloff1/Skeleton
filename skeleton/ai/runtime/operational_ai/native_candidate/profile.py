"""Source-bound reproducibility profile; prevents anonymous candidate delivery."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import digest, identity, sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class ReproducibilityProfile:
    git_sha: str
    trainer_sha: str
    model_sha: str
    tokenizer_sha: str
    source_sha: str
    split_sha: str
    rights_sha: str
    python_version: str
    platform_tag: str

    def __post_init__(self) -> None:
        for k in ("git_sha", "trainer_sha", "model_sha", "tokenizer_sha",
                  "source_sha", "split_sha", "rights_sha"):
            sha(getattr(self, k), k)
        identity(self.python_version, "python")
        identity(self.platform_tag, "platform")

    def record(self) -> dict:
        return {
            "schema": "skeleton.native-candidate.reproducibility.v1",
            **{k: getattr(self, k) for k in self.__dataclass_fields__},
            "cross_platform_reproduced": False,
            "model_quality_verified": False,
            "release_certified": False,
        }

    @property
    def digest(self) -> str:
        return digest(self.record())
