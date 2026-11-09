"""Metadata-only manifests for authorized local/open model artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from math import prod
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest

_DTYPE_BYTES = {
    "bool": 1,
    "int8": 1,
    "uint8": 1,
    "float8": 1,
    "int16": 2,
    "float16": 2,
    "bfloat16": 2,
    "int32": 4,
    "float32": 4,
    "int64": 8,
    "float64": 8,
}


@dataclass(frozen=True)
class TensorRecord:
    name: str
    shape: tuple[int, ...]
    dtype: str
    provenance_receipt: str
    content_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ReverseEngineeringError("tensor record requires name")
        if not self.shape or any(dim <= 0 for dim in self.shape):
            raise ReverseEngineeringError("tensor shape must contain positive dimensions")
        if len(self.provenance_receipt) != 64:
            raise ReverseEngineeringError("tensor record requires a provenance receipt")
        if self.content_digest is not None and len(self.content_digest) != 64:
            raise ReverseEngineeringError("content_digest must be sha256 length")

    @property
    def parameter_count(self) -> int:
        return prod(self.shape)

    @property
    def estimated_bytes(self) -> int | None:
        width = _DTYPE_BYTES.get(self.dtype.lower())
        return None if width is None else self.parameter_count * width


@dataclass(frozen=True)
class ArtifactManifest:
    tensor_count: int
    parameter_count: int
    known_storage_bytes: int
    unknown_dtype_tensors: int
    dtype_counts: tuple[tuple[str, int], ...]
    rank_counts: tuple[tuple[int, int], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tensor_count": self.tensor_count,
            "parameter_count": self.parameter_count,
            "known_storage_bytes": self.known_storage_bytes,
            "unknown_dtype_tensors": self.unknown_dtype_tensors,
            "dtype_counts": [list(item) for item in self.dtype_counts],
            "rank_counts": [list(item) for item in self.rank_counts],
            "digest": self.digest,
        }


def build_artifact_manifest(records: Sequence[TensorRecord]) -> ArtifactManifest:
    if not records:
        raise ReverseEngineeringError("artifact manifest requires tensor records")
    names = [record.name for record in records]
    if len(names) != len(set(names)):
        raise ReverseEngineeringError("tensor names must be unique")
    dtype_counts: dict[str, int] = {}
    rank_counts: dict[int, int] = {}
    known_bytes = 0
    unknown = 0
    for record in records:
        dtype = record.dtype.lower()
        dtype_counts[dtype] = dtype_counts.get(dtype, 0) + 1
        rank_counts[len(record.shape)] = rank_counts.get(len(record.shape), 0) + 1
        size = record.estimated_bytes
        if size is None:
            unknown += 1
        else:
            known_bytes += size
    ordered = sorted(records, key=lambda item: item.name)
    payload = {
        "records": [
            {
                "name": record.name,
                "shape": list(record.shape),
                "dtype": record.dtype.lower(),
                "provenance_receipt": record.provenance_receipt,
                "content_digest": record.content_digest,
            }
            for record in ordered
        ]
    }
    return ArtifactManifest(
        tensor_count=len(ordered),
        parameter_count=sum(record.parameter_count for record in ordered),
        known_storage_bytes=known_bytes,
        unknown_dtype_tensors=unknown,
        dtype_counts=tuple(sorted(dtype_counts.items())),
        rank_counts=tuple(sorted(rank_counts.items())),
        digest=stable_digest(payload),
    )
