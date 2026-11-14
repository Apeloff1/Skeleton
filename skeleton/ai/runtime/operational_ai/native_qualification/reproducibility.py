"""Versioned metadata linking exact corpus, native runtime, model and tokenizer."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import encode, hex64, identity, sha256
from .contracts import ModelIdentity
from .errors import deny


@dataclass(frozen=True, slots=True)
class ExperimentBinding:
    model: ModelIdentity
    corpus_sha256: str
    git_commit: str
    runtime_tag: str
    command_profile_sha256: str
    execution_kind: str = "native-local"

    def __post_init__(self) -> None:
        if type(self.model) is not ModelIdentity:
            deny("binding-model")
        for name in ("corpus_sha256", "command_profile_sha256"):
            hex64(getattr(self, name), name)
        if type(self.git_commit) is not str or len(self.git_commit) != 40:
            deny("binding-git-commit")
        if any(c not in "0123456789abcdef" for c in self.git_commit):
            deny("binding-git-commit")
        identity(self.runtime_tag, "runtime-tag")
        if self.execution_kind != "native-local":
            deny("binding-hosted-not-authorized")

    def record(self) -> dict:
        return {
            "schema": "skeleton.native-qualification.binding.v1",
            "model": self.model.record(), "corpus_sha256": self.corpus_sha256,
            "git_commit": self.git_commit, "runtime_tag": self.runtime_tag,
            "command_profile_sha256": self.command_profile_sha256,
            "execution_kind": self.execution_kind,
        }

    @property
    def digest(self) -> str:
        return sha256(encode(self.record()))
