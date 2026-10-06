"""Fail-closed admission for model artifacts before parsing or loading.

This module is intentionally parser/framework agnostic.  It defines the
resource, format, metadata and trust envelope that a concrete loader must
satisfy before it is allowed to touch privileged model state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath


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


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArtifactLoadError(f"{name} must be a non-negative integer")
    return value


def _artifact_path(name: str, value: object) -> str:
    path = _text(name, value, maximum=2048)
    if "\x00" in path or "\\" in path:
        raise ArtifactLoadError(f"{name} must be a canonical artifact-relative path")
    pure = PurePosixPath(path)
    parts = pure.parts
    if (
        pure.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or pure.as_posix() != path
    ):
        raise ArtifactLoadError(f"{name} must be a canonical artifact-relative path")
    first = parts[0]
    if len(first) == 2 and first[0].isalpha() and first[1] == ":":
        raise ArtifactLoadError(f"{name} must be a canonical artifact-relative path")
    return path


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
        raise ArtifactLoadError("artifact evidence must be deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


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
    max_tensors: int = 1_000_000
    max_total_tensor_elements: int = 1 << 40
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
            "max_tensors",
            "max_total_tensor_elements",
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
        for field_name in ("require_safe_parser", "allow_embedded_executable_code"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed_weight_formats": list(self.allowed_weight_formats),
            "allowed_dtypes": list(self.allowed_dtypes),
            "max_shards": self.max_shards,
            "max_total_bytes": self.max_total_bytes,
            "max_single_shard_bytes": self.max_single_shard_bytes,
            "max_metadata_bytes": self.max_metadata_bytes,
            "max_tensor_rank": self.max_tensor_rank,
            "max_tensor_elements": self.max_tensor_elements,
            "max_tensors": self.max_tensors,
            "max_total_tensor_elements": self.max_total_tensor_elements,
            "max_decompression_ratio": self.max_decompression_ratio,
            "require_safe_parser": self.require_safe_parser,
            "allow_embedded_executable_code": self.allow_embedded_executable_code,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


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

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "element_count": self.element_count,
        }


@dataclass(frozen=True, slots=True)
class ArtifactShard:
    name: str
    digest: str
    encoded_bytes: int
    decoded_bytes: int
    tensors: tuple[TensorDescriptor, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _artifact_path("shard name", self.name))
        object.__setattr__(self, "digest", _sha("shard digest", self.digest))
        for field_name in ("encoded_bytes", "decoded_bytes"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ArtifactLoadError(f"{field_name} must be a positive integer")
        if any(not isinstance(item, TensorDescriptor) for item in self.tensors):
            raise TypeError("tensors must contain TensorDescriptor values")
        tensor_names = [item.name for item in self.tensors]
        if len(tensor_names) != len(set(tensor_names)):
            raise ArtifactLoadError("tensor names within a shard must be unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "digest": self.digest,
            "encoded_bytes": self.encoded_bytes,
            "decoded_bytes": self.decoded_bytes,
            "tensors": [item.as_dict() for item in self.tensors],
        }


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
        tensor_names = [
            tensor.name
            for shard in self.shards
            for tensor in shard.tensors
        ]
        if len(tensor_names) != len(set(tensor_names)):
            raise ArtifactLoadError(
                "tensor names must be globally unique across artifact shards"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "weight_format": self.weight_format,
            "shards": [item.as_dict() for item in self.shards],
            "metadata_bytes": self.metadata_bytes,
            "safe_parser": self.safe_parser,
            "embedded_executable_code": self.embedded_executable_code,
            "model_code_digest": self.model_code_digest,
            "trusted_model_code_digest": self.trusted_model_code_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ArtifactLoadReceipt:
    artifact_id: str
    admitted: bool
    total_encoded_bytes: int
    total_decoded_bytes: int
    tensor_count: int
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _text("artifact_id", self.artifact_id))
        if not isinstance(self.admitted, bool):
            raise TypeError("admitted must be boolean")
        for field_name in (
            "total_encoded_bytes",
            "total_decoded_bytes",
            "tensor_count",
        ):
            object.__setattr__(
                self,
                field_name,
                _non_negative_int(field_name, getattr(self, field_name)),
            )
        blockers = tuple(_text("blocker", item, maximum=4096) for item in self.blockers)
        if self.admitted and blockers:
            raise ArtifactLoadError("admitted artifact cannot contain blockers")
        if not self.admitted and not blockers:
            raise ArtifactLoadError("rejected artifact must explain at least one blocker")
        object.__setattr__(self, "blockers", blockers)

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "admitted": self.admitted,
            "total_encoded_bytes": self.total_encoded_bytes,
            "total_decoded_bytes": self.total_decoded_bytes,
            "tensor_count": self.tensor_count,
            "blockers": list(self.blockers),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ArtifactAdmissionEvidence:
    request_digest: str
    policy_digest: str
    receipt: ArtifactLoadReceipt

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_digest", _sha("request_digest", self.request_digest)
        )
        object.__setattr__(
            self, "policy_digest", _sha("policy_digest", self.policy_digest)
        )
        if not isinstance(self.receipt, ArtifactLoadReceipt):
            raise TypeError("receipt must be ArtifactLoadReceipt")

    def as_dict(self) -> dict[str, object]:
        return {
            "request_digest": self.request_digest,
            "policy_digest": self.policy_digest,
            "receipt": self.receipt.as_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ManifestLoadBinding:
    artifact_id: str
    manifest_weight_identity: str
    request_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _text("artifact_id", self.artifact_id))
        object.__setattr__(
            self,
            "manifest_weight_identity",
            _sha("manifest_weight_identity", self.manifest_weight_identity),
        )
        object.__setattr__(
            self, "request_digest", _sha("request_digest", self.request_digest)
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "artifact_id": self.artifact_id,
                "manifest_weight_identity": self.manifest_weight_identity,
                "request_digest": self.request_digest,
            }
        )


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
    total_tensor_elements = 0
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
            total_tensor_elements += tensor.element_count
            if tensor.dtype not in policy.allowed_dtypes:
                blockers.append(f"{shard.name}:{tensor.name}: dtype is not allowlisted")
            if len(tensor.shape) > policy.max_tensor_rank:
                blockers.append(f"{shard.name}:{tensor.name}: tensor rank exceeds policy")
            if tensor.element_count > policy.max_tensor_elements:
                blockers.append(f"{shard.name}:{tensor.name}: tensor elements exceed policy")

    if tensor_count > policy.max_tensors:
        blockers.append("tensor count exceeds policy")
    if total_tensor_elements > policy.max_total_tensor_elements:
        blockers.append("total tensor elements exceed policy")
    if total_encoded > policy.max_total_bytes:
        blockers.append("total encoded artifact size exceeds policy")
    if total_decoded > policy.max_total_bytes:
        blockers.append("total decoded artifact size exceeds policy")

    # Weight/data trust never grants model-code trust.  If executable model
    # code is present, its identity must be separately and exactly authorized.
    if request.embedded_executable_code and request.model_code_digest is None:
        blockers.append("embedded executable model code has no content digest")
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


def admit_artifact_evidence(
    request: ArtifactLoadRequest,
    policy: ArtifactLoadPolicy,
) -> ArtifactAdmissionEvidence:
    receipt = admit_artifact(request, policy)
    return ArtifactAdmissionEvidence(
        request_digest=request.digest,
        policy_digest=policy.digest,
        receipt=receipt,
    )


def bind_model_manifest(
    manifest: object,
    request: ArtifactLoadRequest,
) -> ManifestLoadBinding:
    """Bind a model identity manifest to the exact bytes admitted for loading."""

    from .model_identity import ModelArtifactManifest

    if not isinstance(manifest, ModelArtifactManifest):
        raise TypeError("manifest must be ModelArtifactManifest")
    if not isinstance(request, ArtifactLoadRequest):
        raise TypeError("request must be ArtifactLoadRequest")
    if request.artifact_id != manifest.artifact_id:
        raise ArtifactLoadError("load request artifact identity does not match manifest")
    if request.weight_format != manifest.weight_format:
        raise ArtifactLoadError("load request weight format does not match manifest")

    expected = {
        shard.path: (shard.digest, shard.size_bytes)
        for shard in manifest.weight_shards
    }
    observed = {
        shard.name: (shard.digest, shard.encoded_bytes)
        for shard in request.shards
    }
    if observed != expected:
        raise ArtifactLoadError(
            "load request shard set/digest/size does not match manifest"
        )
    if request.model_code_digest != manifest.model_code_digest:
        raise ArtifactLoadError("load request model code identity does not match manifest")
    if (
        request.trusted_model_code_digest is not None
        and request.trusted_model_code_digest != manifest.model_code_digest
    ):
        raise ArtifactLoadError(
            "trusted model code identity does not match manifest"
        )

    return ManifestLoadBinding(
        artifact_id=manifest.artifact_id,
        manifest_weight_identity=manifest.weight_identity,
        request_digest=request.digest,
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
    "ArtifactAdmissionEvidence",
    "ArtifactLoadError",
    "ArtifactLoadPolicy",
    "ArtifactLoadReceipt",
    "ArtifactLoadRequest",
    "ArtifactShard",
    "ManifestLoadBinding",
    "TensorDescriptor",
    "admit_artifact",
    "admit_artifact_evidence",
    "bind_model_manifest",
    "digest_bytes",
    "verify_shard_payload",
]
