"""Immutable representation and model-artifact identity contracts.

These contracts close the ambiguity between "weights exist" and "this exact
model can be reproduced and loaded safely".  A model identity binds its
representation/tokenizer, architecture, weight shards, runtime ABI, lineage,
and evaluation/provenance roots.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Mapping, Sequence


class ModelIdentityError(RuntimeError):
    """Model identity or component binding is incomplete or inconsistent."""


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ModelIdentityError("identity value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelIdentityError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ModelIdentityError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ModelIdentityError(f"{name} must be lowercase sha256")
    return result


def _artifact_path(name: str, value: object) -> str:
    path = _text(name, value, maximum=2048)
    if value != path or "\x00" in path or "\\" in path:
        raise ModelIdentityError(f"{name} must be a canonical artifact-relative path")
    pure = PurePosixPath(path)
    parts = pure.parts
    if (
        pure.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or pure.as_posix() != path
    ):
        raise ModelIdentityError(f"{name} must be a canonical artifact-relative path")
    first = parts[0]
    if len(first) == 2 and first[0].isalpha() and first[1] == ":":
        raise ModelIdentityError(f"{name} must be a canonical artifact-relative path")
    return path


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        _stable_json(value)
        return value
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ModelIdentityError("metadata object keys must be strings")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ModelIdentityError("metadata contains non-JSON value")


def _thaw_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _unique_text(name: str, values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(_text(name, value) for value in values)
    if len(result) != len(set(result)):
        raise ModelIdentityError(f"{name} values must be unique")
    return result


@dataclass(frozen=True, slots=True)
class RepresentationSpec:
    """Canonical tokenizer / representation dependency for a model artifact."""

    tokenizer_family: str
    tokenizer_version: str
    vocabulary_digest: str
    normalization_spec: str
    byte_fallback_policy: str
    special_token_map: Mapping[str, int]
    bos_token: str | None = None
    eos_token: str | None = None
    padding_token: str | None = None
    compatibility_class: str = "exact"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "tokenizer_family", _text("tokenizer_family", self.tokenizer_family)
        )
        object.__setattr__(
            self, "tokenizer_version", _text("tokenizer_version", self.tokenizer_version)
        )
        object.__setattr__(
            self, "vocabulary_digest", _sha("vocabulary_digest", self.vocabulary_digest)
        )
        object.__setattr__(
            self,
            "normalization_spec",
            _text("normalization_spec", self.normalization_spec),
        )
        object.__setattr__(
            self,
            "byte_fallback_policy",
            _text("byte_fallback_policy", self.byte_fallback_policy),
        )
        if self.compatibility_class not in {"exact", "decode-compatible", "migration-only"}:
            raise ModelIdentityError("unsupported representation compatibility_class")

        tokens: dict[str, int] = {}
        ids: set[int] = set()
        for raw_name, raw_id in self.special_token_map.items():
            name = _text("special token name", raw_name)
            if name in tokens:
                raise ModelIdentityError(
                    "special token names must remain unique after normalization"
                )
            if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id < 0:
                raise ModelIdentityError("special token ids must be non-negative integers")
            if raw_id in ids:
                raise ModelIdentityError("special token ids must be unique")
            tokens[name] = raw_id
            ids.add(raw_id)
        object.__setattr__(
            self,
            "special_token_map",
            MappingProxyType(dict(sorted(tokens.items()))),
        )

        for field_name in ("bos_token", "eos_token", "padding_token"):
            value = getattr(self, field_name)
            if value is None:
                continue
            normalized = _text(field_name, value)
            if normalized not in tokens:
                raise ModelIdentityError(
                    f"{field_name} must reference a declared special token"
                )
            object.__setattr__(self, field_name, normalized)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.representation.v1",
            "tokenizer_family": self.tokenizer_family,
            "tokenizer_version": self.tokenizer_version,
            "vocabulary_digest": self.vocabulary_digest,
            "normalization_spec": self.normalization_spec,
            "byte_fallback_policy": self.byte_fallback_policy,
            "special_token_map": dict(self.special_token_map),
            "bos_token": self.bos_token,
            "eos_token": self.eos_token,
            "padding_token": self.padding_token,
            "compatibility_class": self.compatibility_class,
        }

    @property
    def representation_id(self) -> str:
        return "rep:" + _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class WeightShard:
    path: str
    digest: str
    size_bytes: int

    def __post_init__(self) -> None:
        path = _artifact_path("weight shard path", self.path)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "digest", _sha("weight shard digest", self.digest))
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes <= 0
        ):
            raise ModelIdentityError("weight shard size_bytes must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class ModelArtifactManifest:
    """Complete load/promotion identity for one concrete model artifact."""

    model_id: str
    architecture_id: str
    architecture_config_digest: str
    representation: RepresentationSpec
    weight_shards: tuple[WeightShard, ...]
    weight_format: str
    dtype: str
    quantization: str
    model_code_digest: str
    runtime_abi: str
    data_manifest_root: str
    eval_evidence_root: str
    provenance_root: str
    adapter_set: tuple[str, ...] = ()
    kernel_capability_requirements: tuple[str, ...] = ()
    training_parent: str | None = None
    optimizer_parent: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "model_id",
            "architecture_id",
            "weight_format",
            "dtype",
            "quantization",
            "runtime_abi",
        ):
            object.__setattr__(
                self, field_name, _text(field_name, getattr(self, field_name))
            )
        for field_name in (
            "architecture_config_digest",
            "model_code_digest",
            "data_manifest_root",
            "eval_evidence_root",
            "provenance_root",
        ):
            object.__setattr__(
                self, field_name, _sha(field_name, getattr(self, field_name))
            )
        if not isinstance(self.representation, RepresentationSpec):
            raise TypeError("representation must be RepresentationSpec")
        shards = tuple(self.weight_shards)
        if not shards:
            raise ModelIdentityError("at least one weight shard is required")
        if any(not isinstance(shard, WeightShard) for shard in shards):
            raise TypeError("weight_shards must contain WeightShard values")
        object.__setattr__(self, "weight_shards", shards)
        paths = [shard.path for shard in shards]
        if len(paths) != len(set(paths)):
            raise ModelIdentityError("weight shard paths must be unique")
        object.__setattr__(
            self, "adapter_set", _unique_text("adapter", self.adapter_set)
        )
        object.__setattr__(
            self,
            "kernel_capability_requirements",
            _unique_text(
                "kernel capability", self.kernel_capability_requirements
            ),
        )
        for field_name in ("training_parent", "optimizer_parent"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self, field_name, _sha(field_name, value)
                )
        raw_metadata = dict(self.metadata)
        _stable_json(raw_metadata)
        object.__setattr__(self, "metadata", _freeze_json(raw_metadata))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.model_artifact_manifest.v1",
            "model_id": self.model_id,
            "architecture_id": self.architecture_id,
            "architecture_config_digest": self.architecture_config_digest,
            "representation_id": self.representation.representation_id,
            "representation": self.representation.as_dict(),
            "weight_shards": [shard.as_dict() for shard in self.weight_shards],
            "weight_format": self.weight_format,
            "dtype": self.dtype,
            "quantization": self.quantization,
            "adapter_set": list(self.adapter_set),
            "model_code_digest": self.model_code_digest,
            "runtime_abi": self.runtime_abi,
            "kernel_capability_requirements": list(
                self.kernel_capability_requirements
            ),
            "training_parent": self.training_parent,
            "optimizer_parent": self.optimizer_parent,
            "data_manifest_root": self.data_manifest_root,
            "eval_evidence_root": self.eval_evidence_root,
            "provenance_root": self.provenance_root,
            "metadata": _thaw_json(self.metadata),
        }

    @property
    def artifact_id(self) -> str:
        return "model:" + _digest(self.as_dict())

    @property
    def total_weight_bytes(self) -> int:
        return sum(shard.size_bytes for shard in self.weight_shards)

    @property
    def weight_identity(self) -> str:
        return _digest(
            [shard.as_dict() for shard in self.weight_shards]
        )

    def validate_loaded_components(
        self,
        *,
        representation_id: str,
        model_code_digest: str,
        weight_digests: Mapping[str, str],
        runtime_abi: str,
    ) -> None:
        """Fail closed when loaded components differ from the manifest."""

        if representation_id != self.representation.representation_id:
            raise ModelIdentityError("loaded representation identity mismatch")
        if _sha("loaded model_code_digest", model_code_digest) != self.model_code_digest:
            raise ModelIdentityError("loaded model code identity mismatch")
        if _text("loaded runtime_abi", runtime_abi) != self.runtime_abi:
            raise ModelIdentityError("loaded runtime ABI mismatch")

        expected = {shard.path: shard.digest for shard in self.weight_shards}
        observed: dict[str, str] = {}
        for path, digest in weight_digests.items():
            normalized_path = _artifact_path("loaded weight path", path)
            if normalized_path in observed:
                raise ModelIdentityError(
                    "loaded weight paths collide after normalization"
                )
            observed[normalized_path] = _sha("loaded weight digest", digest)
        if observed != expected:
            raise ModelIdentityError("loaded weight shard set/digest mismatch")


__all__ = [
    "ModelArtifactManifest",
    "ModelIdentityError",
    "RepresentationSpec",
    "WeightShard",
]
