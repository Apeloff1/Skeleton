"""Attention-head geometry inference from authorized model metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


class AttentionMode(str, Enum):
    MHA = "multi_head_attention"
    GQA = "grouped_query_attention"
    MQA = "multi_query_attention"


@dataclass(frozen=True)
class AttentionLayerShape:
    layer_index: int
    query_heads: int
    key_value_heads: int
    head_dim: int
    model_width: int | None = None

    def __post_init__(self) -> None:
        if self.layer_index < 0:
            raise ReverseEngineeringError("layer_index must be non-negative")
        if self.query_heads <= 0 or self.key_value_heads <= 0 or self.head_dim <= 0:
            raise ReverseEngineeringError("attention dimensions must be positive")
        if self.key_value_heads > self.query_heads:
            raise ReverseEngineeringError("key_value_heads cannot exceed query_heads")
        if self.query_heads % self.key_value_heads != 0:
            raise ReverseEngineeringError("query_heads must be divisible by key_value_heads")
        if self.model_width is not None and self.model_width <= 0:
            raise ReverseEngineeringError("model_width must be positive when present")

    @property
    def mode(self) -> AttentionMode:
        if self.key_value_heads == self.query_heads:
            return AttentionMode.MHA
        if self.key_value_heads == 1:
            return AttentionMode.MQA
        return AttentionMode.GQA

    @property
    def query_to_kv_ratio(self) -> int:
        return self.query_heads // self.key_value_heads


@dataclass(frozen=True)
class AttentionGeometryReport:
    layer_count: int
    mode_counts: tuple[tuple[str, int], ...]
    uniform_mode: str | None
    query_head_counts: tuple[int, ...]
    key_value_head_counts: tuple[int, ...]
    query_to_kv_ratios: tuple[int, ...]
    width_mismatch_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_count": self.layer_count,
            "mode_counts": [list(item) for item in self.mode_counts],
            "uniform_mode": self.uniform_mode,
            "query_head_counts": list(self.query_head_counts),
            "key_value_head_counts": list(self.key_value_head_counts),
            "query_to_kv_ratios": list(self.query_to_kv_ratios),
            "width_mismatch_count": self.width_mismatch_count,
            "digest": self.digest,
        }


def analyze_attention_geometry(
    layers: Sequence[AttentionLayerShape],
) -> AttentionGeometryReport:
    if not layers:
        raise ReverseEngineeringError("attention geometry requires layers")
    ordered = sorted(layers, key=lambda item: item.layer_index)
    indices = [item.layer_index for item in ordered]
    if len(indices) != len(set(indices)):
        raise ReverseEngineeringError("attention layer indices must be unique")

    modes: dict[str, int] = {}
    width_mismatch = 0
    for item in ordered:
        modes[item.mode.value] = modes.get(item.mode.value, 0) + 1
        if item.model_width is not None and item.query_heads * item.head_dim != item.model_width:
            width_mismatch += 1
    uniform = next(iter(modes)) if len(modes) == 1 else None
    payload = {
        "layers": [
            {
                "layer_index": item.layer_index,
                "query_heads": item.query_heads,
                "key_value_heads": item.key_value_heads,
                "head_dim": item.head_dim,
                "model_width": item.model_width,
                "mode": item.mode.value,
            }
            for item in ordered
        ]
    }
    return AttentionGeometryReport(
        layer_count=len(ordered),
        mode_counts=tuple(sorted(modes.items())),
        uniform_mode=uniform,
        query_head_counts=tuple(sorted({item.query_heads for item in ordered})),
        key_value_head_counts=tuple(sorted({item.key_value_heads for item in ordered})),
        query_to_kv_ratios=tuple(sorted({item.query_to_kv_ratio for item in ordered})),
        width_mismatch_count=width_mismatch,
        digest=stable_digest(payload),
    )
