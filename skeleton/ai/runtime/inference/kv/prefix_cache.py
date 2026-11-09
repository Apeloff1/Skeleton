from dataclasses import dataclass
from collections.abc import Collection


@dataclass(frozen=True)
class PrefixCacheKey:
    instruction_digest: str
    prompt_digest: str
    model: str
    tokenizer: str
    version: str
    scope: str

    @property
    def complete(self) -> bool:
        return all(
            (
                self.instruction_digest,
                self.prompt_digest,
                self.model,
                self.tokenizer,
                self.version,
                self.scope,
            )
        )


@dataclass(frozen=True)
class PrefixArtifact:
    key: PrefixCacheKey
    sensitive: bool

    def __post_init__(self) -> None:
        if not isinstance(self.key, PrefixCacheKey) or not isinstance(self.sensitive, bool):
            raise ValueError("valid prefix artifact required")


@dataclass(frozen=True)
class PrefixReuseDecision:
    reusable: bool
    reason: str


def can_reuse(
    artifact: PrefixArtifact,
    key: PrefixCacheKey,
    authorized_scopes: Collection[str],
) -> PrefixReuseDecision:
    if not isinstance(artifact, PrefixArtifact) or not isinstance(key, PrefixCacheKey):
        return PrefixReuseDecision(False, "invalid cache artifact")
    if isinstance(authorized_scopes, (str, bytes)) or not isinstance(
        authorized_scopes, Collection
    ):
        return PrefixReuseDecision(False, "invalid authorized scopes")
    if not key.complete or not artifact.key.complete:
        return PrefixReuseDecision(False, "incomplete cache identity")
    if artifact.key != key:
        return PrefixReuseDecision(False, "identity mismatch")
    if key.scope not in authorized_scopes:
        return PrefixReuseDecision(False, "scope denied")
    return PrefixReuseDecision(True, "exact identity and scope")
