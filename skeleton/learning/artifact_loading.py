"""Fail-closed admission for model artifacts before parsing or loading.

This module is intentionally parser/framework agnostic.  It defines the
resource, format, metadata and trust envelope that a concrete loader must
satisfy before it is allowed to touch privileged model state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping, Sequence


class ArtifactLoadError(RuntimeError):
    """An artifact cannot be admitted safely for parsing/loading."""


def _text(name: str, value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactLoadError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ArtifactLoadError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ArtifactLoadError(f"{name} must be lowercase sha256")
    return result


def digest_bytes(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactLoadPolicy:
    allowed_weight_formats: tuple[str, ...] = ("safetensors",)
    allowed_dtypes: tuple[str, ...] = ("bf16", "fp16", "fp32", "int8", "int4")
    max_shards: int = 1024
    max_total_bytes: int = 1 << 40
    max_single_shard_bytes: int = 1 << 38
    max_metadata_bytes: int = 16 << 20
    max_tensor_rank: int = 8
    max_tensor_elements: int = 1 << 40
    max_decompression_ratio: int = 64
    require_safe_parser: bool = True
    allow_embedded_executable_code: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "max_shards",
            "max_total_bytes",
            "max_single_shard_bytes",
            "max_metadata_bytes",
            "max_tensor_rank",
            "max_tensor_elements",
            "max_decompression_ratio",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ArtifactLoadError(f"{field_name} must be a positive integer")
        formats = tuple(_text("weight format", item) for item in self.allowed_weight_formats)
        dtypes = tuple(_text("dtype", item) for item in self.allowed_dtypes)
        if not formats or len(formats) != len(set(formats)):
            raise ArtifactLoadError("allowed_weight_formats must be non-empty and unique")
        if not dtypes or len(dtypes) != len(set(dtypes)):
            raise ArtifactLoadError("allowed_dtypes must be non-empty and unique")
        object.__setattr__(self, "allowed_weight_formats", formats)
        object.__setattr__(self, "allowed_dtypes", dtypes)


@dataclass(frozen=True, slots=True)
class TensorDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text("tensor name", self.name))
        object.__setattr__(self, "dtype", _text("tensor dtype", self.dtype))
        if not self.shape:
            raise ArtifactLoadError("tensor shape must not be empty")
        normalized: list[int] = []
        for dim in self.shape:
            if isinstance(dim, bool) or not isinstance(dim, int) or dim <= 0:
                raise ArtifactLoadError("tensor dimensions must be positive integers")
            normalized.append(dim)
        object.__setattr__(self, "shape", tuple(normalized))

    @property
    def element_count(self) -> int:
        total = 1
        for dim in self.shape:
            total *= dim
        return total


@dataclass(frozen=True, slots=True)
class ArtifactShard:
    name: str
    digest: str
    encoded_bytes: int
    decoded_bytes: int
    tensors: tuple[TensorDescriptor, ...] = ()

    def __post_init__(self) -> None:
        name = _text("shard name", self.name)
        if name.startswith("/") or "\\" in name or ".." in name.split("/"):
            raise ArtifactLoadError("shard name must be artifact-relative")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "digest", _sha("shard digest", self.digest))
        for field_name in ("encoded_bytes", "decoded_bytes"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ArtifactLoadError(f"{field_name} must be a positive integer")
        if any(not isinstance(item, TensorDescriptor) for item in self.tensors):
            raise TypeError("tensors must contain TensorDescriptor values")


@dataclass(frozen=True, slots=True)
class ArtifactLoadRequest:
    artifact_id: str
    weight_format: str
    shards: tuple[ArtifactShard, ...]
    metadata_bytes: int
    safe_parser: bool
    embedded_executable_code: bool
    model_code_digest: str | None = None
    trusted_model_code_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _text("artifact_id", self.artifact_id))
        object.__setattr__(self, "weight_format", _text("weight_format", self.weight_format))
        if not self.shards:
            raise ArtifactLoadError("artifact requires at least one shard")
        if any(not isinstance(item, ArtifactShard) for item in self.shards):
            raise TypeError("shards must contain ArtifactShard values")
        names = [item.name for item in self.shards]
        if len(names) != len(set(names)):
            raise ArtifactLoadError("shard names must be unique")
        if isinstance(self.metadata_bytes, bool) or not isinstance(self.metadata_bytes, int):
            raise ArtifactLoadError("metadata_bytes must be an integer")
        if self.metadata_bytes < 0:
            raise ArtifactLoadError("metadata_bytes must be non-negative")
        for field_name in ("safe_parser", "embedded_executable_code"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be boolean")
        if self.model_code_digest is not None:
            object.__setattr__(
                self, "model_code_digest", _sha("model_code_digest", self.model_code_digest)
            )
        if self.trusted_model_code_digest is not None:
            object.__setattr__(
                self,
                "trusted_model_code_digest",
                _sha("trusted_model_code_digest", self.trusted_model_code_digest),
            )


@dataclass(frozen=True, slots=True)
class ArtifactLoadReceipt:
    artifact_id: str
    admitted: bool
    total_encoded_bytes: int
    total_decoded_bytes: int
    tensor_count: int
    blockers: tuple[str, ...]


def admit_artifact(
    request: ArtifactLoadRequest,
    policy: ArtifactLoadPolicy,
) -> ArtifactLoadReceipt:
    if not isinstance(request, ArtifactLoadRequest):
        raise TypeError("request must be ArtifactLoadRequest")
    if not isinstance(policy, ArtifactLoadPolicy):
        raise TypeError("policy must be ArtifactLoadPolicy")

    blockers: list[str] = []
    if request.weight_format not in policy.allowed_weight_formats:
        blockers.append("weight format is not allowlisted")
    if len(request.shards) > policy.max_shards:
        blockers.append("shard count exceeds policy")
    if request.metadata_bytes > policy.max_metadata_bytes:
        blockers.append("metadata size exceeds policy")
    if policy.require_safe_parser and not request.safe_parser:
        blockers.append("safe parser declaration is required")
    if request.embedded_executable_code and not policy.allow_embedded_executable_code:
        blockers.append("embedded executable model code is forbidden")

    total_encoded = 0
    total_decoded = 0
    tensor_count = 0
    for shard in request.shards:
        total_encoded += shard.encoded_bytes
        total_decoded += shard.decoded_bytes
        if shard.encoded_bytes > policy.max_single_shard_bytes:
            blockers.append(f"{shard.name}: encoded shard size exceeds policy")
        if shard.decoded_bytes > policy.max_single_shard_bytes:
            blockers.append(f"{shard.name}: decoded shard size exceeds policy")
        if shard.decoded_bytes > shard.encoded_bytes * policy.max_decompression_ratio:
            blockers.append(f"{shard.name}: decompression ratio exceeds policy")
        for tensor in shard.tensors:
            tensor_count += 1
            if tensor.dtype not in policy.allowed_dtypes:
                blockers.append(f"{shard.name}:{tensor.name}: dtype is not allowlisted")
            if len(tensor.shape) > policy.max_tensor_rank:
                blockers.append(f"{shard.name}:{tensor.name}: tensor rank exceeds policy")
            if tensor.element_count > policy.max_tensor_elements:
                blockers.append(f"{shard.name}:{tensor.name}: tensor elements exceed policy")

    if total_encoded > policy.max_total_bytes:
        blockers.append("total encoded artifact size exceeds policy")
    if total_decoded > policy.max_total_bytes:
        blockers.append("total decoded artifact size exceeds policy")

    # Weight/data trust never grants model-code trust.  If executable model
    # code is present, its identity must be separately and exactly authorized.
    if request.model_code_digest is not None:
        if request.trusted_model_code_digest is None:
            blockers.append("model code has no independent trusted digest")
        elif request.model_code_digest != request.trusted_model_code_digest:
            blockers.append("model code digest does not match trusted identity")
    elif request.trusted_model_code_digest is not None:
        blockers.append("trusted model code identity supplied without model code")

    return ArtifactLoadReceipt(
        artifact_id=request.artifact_id,
        admitted=not blockers,
        total_encoded_bytes=total_encoded,
        total_decoded_bytes=total_decoded,
        tensor_count=tensor_count,
        blockers=tuple(blockers),
    )


def verify_shard_payload(shard: ArtifactShard, payload: bytes) -> None:
    if not isinstance(shard, ArtifactShard):
        raise TypeError("shard must be ArtifactShard")
    observed = digest_bytes(payload)
    if observed != shard.digest:
        raise ArtifactLoadError(f"{shard.name}: payload digest mismatch")
    if len(payload) != shard.encoded_bytes:
        raise ArtifactLoadError(f"{shard.name}: encoded size mismatch")


__all__ = [
    "ArtifactLoadError",
    "ArtifactLoadPolicy",
    "ArtifactLoadReceipt",
    "ArtifactLoadRequest",
    "ArtifactShard",
    "TensorDescriptor",
    "admit_artifact",
    "digest_bytes",
    "verify_shard_payload",
]
