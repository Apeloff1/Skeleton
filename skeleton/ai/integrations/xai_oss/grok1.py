"""Governed descriptors for the Apache-2.0 Grok-1 open-weight release."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Grok1Architecture:
    parameters_billions: float = 314.0
    active_parameters_billions: float = 86.0
    experts: int = 8
    active_experts_per_token: int = 2
    layers: int = 64
    query_heads: int = 48
    key_value_heads: int = 8
    embedding_size: int = 6144
    vocabulary_size: int = 131072
    maximum_context_tokens: int = 8192

    def __post_init__(self) -> None:
        integer_fields = (
            self.experts,
            self.active_experts_per_token,
            self.layers,
            self.query_heads,
            self.key_value_heads,
            self.embedding_size,
            self.vocabulary_size,
            self.maximum_context_tokens,
        )
        if any(value <= 0 for value in integer_fields):
            raise ValueError("Grok-1 architecture dimensions must be positive")
        if self.active_experts_per_token > self.experts:
            raise ValueError("active experts cannot exceed total experts")


@dataclass(frozen=True, slots=True)
class Grok1WeightArtifact:
    root: Path
    expected_files: tuple[str, ...] = ("ckpt-0",)

    def __post_init__(self) -> None:
        if not self.expected_files:
            raise ValueError("expected_files must be non-empty")
        if any(not item or Path(item).is_absolute() for item in self.expected_files):
            raise ValueError("weight paths must be non-empty and relative")

    def validate_local(self) -> tuple[bool, tuple[str, ...]]:
        missing = tuple(
            item for item in self.expected_files if not (self.root / item).exists()
        )
        return (not missing, missing)


@dataclass(frozen=True, slots=True)
class Grok1ModelMaterialization:
    artifact: Grok1WeightArtifact
    allow_network_download: bool = False
    source_uri: str | None = None
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.allow_network_download and not self.source_uri:
            raise ValueError("network materialization requires an explicit source_uri")
        if self.expected_sha256 is not None:
            digest = self.expected_sha256.lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")

    def require_local_or_explicit_network(self) -> None:
        ready, missing = self.artifact.validate_local()
        if ready:
            return
        if not self.allow_network_download:
            raise RuntimeError(
                "Grok-1 weights are not local and implicit network download is disabled: "
                + ", ".join(missing)
            )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


GROK1_ARCHITECTURE = Grok1Architecture()


__all__ = [
    "GROK1_ARCHITECTURE",
    "Grok1Architecture",
    "Grok1ModelMaterialization",
    "Grok1WeightArtifact",
    "file_sha256",
]
