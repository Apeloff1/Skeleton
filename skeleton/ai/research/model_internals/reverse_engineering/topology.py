"""Conservative topology inference from authorized tensor metadata."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Sequence

from .artifact_manifest import TensorRecord
from .contracts import ReverseEngineeringError, stable_digest

_LAYER_RE = re.compile(r"(?:^|[./_])(?:layers?|blocks?|h)[./_](\d+)(?:[./_]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class TopologyReport:
    tensor_count: int
    indexed_layer_count: int
    min_layer_index: int | None
    max_layer_index: int | None
    contiguous_layer_indices: bool
    layer_tensor_counts: tuple[tuple[int, int], ...]
    unindexed_tensor_count: int
    recurrent_shape_groups: tuple[tuple[tuple[int, ...], int], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tensor_count": self.tensor_count,
            "indexed_layer_count": self.indexed_layer_count,
            "min_layer_index": self.min_layer_index,
            "max_layer_index": self.max_layer_index,
            "contiguous_layer_indices": self.contiguous_layer_indices,
            "layer_tensor_counts": [list(item) for item in self.layer_tensor_counts],
            "unindexed_tensor_count": self.unindexed_tensor_count,
            "recurrent_shape_groups": [
                [list(shape), count] for shape, count in self.recurrent_shape_groups
            ],
            "digest": self.digest,
        }


def infer_tensor_topology(records: Sequence[TensorRecord]) -> TopologyReport:
    if not records:
        raise ReverseEngineeringError("topology inference requires tensor records")
    layer_counts: dict[int, int] = {}
    shape_counts: dict[tuple[int, ...], int] = {}
    unindexed = 0
    evidence: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: item.name):
        shape_counts[record.shape] = shape_counts.get(record.shape, 0) + 1
        match = _LAYER_RE.search(record.name)
        layer_index = int(match.group(1)) if match else None
        if layer_index is None:
            unindexed += 1
        else:
            layer_counts[layer_index] = layer_counts.get(layer_index, 0) + 1
        evidence.append(
            {"name": record.name, "shape": list(record.shape), "layer_index": layer_index}
        )

    indices = sorted(layer_counts)
    contiguous = True
    if indices:
        contiguous = indices == list(range(indices[0], indices[-1] + 1))
    recurrent = tuple(
        sorted(
            ((shape, count) for shape, count in shape_counts.items() if count > 1),
            key=lambda item: (item[0], item[1]),
        )
    )
    return TopologyReport(
        tensor_count=len(records),
        indexed_layer_count=len(indices),
        min_layer_index=indices[0] if indices else None,
        max_layer_index=indices[-1] if indices else None,
        contiguous_layer_indices=contiguous,
        layer_tensor_counts=tuple(sorted(layer_counts.items())),
        unindexed_tensor_count=unindexed,
        recurrent_shape_groups=recurrent,
        digest=stable_digest({"evidence": evidence}),
    )
