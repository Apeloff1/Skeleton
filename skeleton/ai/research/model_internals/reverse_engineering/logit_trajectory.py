"""Logit-lens trajectory summaries for authorized local/open models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class LogitLensSnapshot:
    sample_id: str
    input_digest: str
    layer_index: int
    top_token_id: int
    top_probability: float
    entropy_proxy: float | None = None

    def __post_init__(self) -> None:
        if not self.sample_id:
            raise ReverseEngineeringError("logit-lens snapshot requires sample_id")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if self.layer_index < 0 or self.top_token_id < 0:
            raise ReverseEngineeringError("layer_index and top_token_id must be non-negative")
        if not isfinite(self.top_probability) or not 0.0 <= self.top_probability <= 1.0:
            raise ReverseEngineeringError("top_probability must be finite and within [0, 1]")
        if self.entropy_proxy is not None and (
            not isfinite(self.entropy_proxy) or self.entropy_proxy < 0.0
        ):
            raise ReverseEngineeringError("entropy_proxy must be finite and non-negative")


@dataclass(frozen=True)
class LogitTrajectoryReport:
    sample_id: str
    snapshot_count: int
    first_layer: int
    final_layer: int
    final_top_token_id: int
    stabilization_layer: int | None
    top_token_change_count: int
    mean_top_probability: float
    final_top_probability: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "snapshot_count": self.snapshot_count,
            "first_layer": self.first_layer,
            "final_layer": self.final_layer,
            "final_top_token_id": self.final_top_token_id,
            "stabilization_layer": self.stabilization_layer,
            "top_token_change_count": self.top_token_change_count,
            "mean_top_probability": self.mean_top_probability,
            "final_top_probability": self.final_top_probability,
            "digest": self.digest,
        }


def _stabilization_layer(items: Sequence[LogitLensSnapshot]) -> int | None:
    final_token = items[-1].top_token_id
    for index, item in enumerate(items):
        if all(later.top_token_id == final_token for later in items[index:]):
            return item.layer_index
    return None


def analyze_logit_trajectory(
    snapshots: Sequence[LogitLensSnapshot],
) -> tuple[LogitTrajectoryReport, ...]:
    if not snapshots:
        raise ReverseEngineeringError("logit trajectory requires snapshots")
    grouped: dict[tuple[str, str], list[LogitLensSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault((snapshot.sample_id, snapshot.input_digest), []).append(snapshot)

    reports: list[LogitTrajectoryReport] = []
    for (sample_id, input_digest), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.layer_index)
        indices = [item.layer_index for item in ordered]
        if len(indices) != len(set(indices)):
            raise ReverseEngineeringError("logit-lens layer indices must be unique within a sample")
        changes = sum(
            left.top_token_id != right.top_token_id
            for left, right in zip(ordered, ordered[1:])
        )
        payload = {
            "sample_id": sample_id,
            "input_digest": input_digest,
            "snapshots": [
                {
                    "layer_index": item.layer_index,
                    "top_token_id": item.top_token_id,
                    "top_probability": item.top_probability,
                    "entropy_proxy": item.entropy_proxy,
                }
                for item in ordered
            ],
        }
        reports.append(
            LogitTrajectoryReport(
                sample_id=sample_id,
                snapshot_count=len(ordered),
                first_layer=ordered[0].layer_index,
                final_layer=ordered[-1].layer_index,
                final_top_token_id=ordered[-1].top_token_id,
                stabilization_layer=_stabilization_layer(ordered),
                top_token_change_count=changes,
                mean_top_probability=sum(item.top_probability for item in ordered) / len(ordered),
                final_top_probability=ordered[-1].top_probability,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
