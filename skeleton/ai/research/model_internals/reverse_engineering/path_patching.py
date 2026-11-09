"""Path-patching summaries for authorized mediator/source/target experiments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class PathPatchObservation:
    observation_id: str
    probe_digest: str
    source_node: str
    mediator_node: str
    target_node: str
    clean_metric: float
    corrupted_metric: float
    patched_metric: float

    def __post_init__(self) -> None:
        if not all((self.observation_id, self.source_node, self.mediator_node, self.target_node)):
            raise ReverseEngineeringError("path-patch identity fields are required")
        if len({self.source_node, self.mediator_node, self.target_node}) < 3:
            raise ReverseEngineeringError("path-patch nodes must be distinct")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if any(
            not isfinite(value)
            for value in (self.clean_metric, self.corrupted_metric, self.patched_metric)
        ):
            raise ReverseEngineeringError("path-patch metrics must be finite")

    @property
    def recoverable_effect(self) -> float:
        return self.clean_metric - self.corrupted_metric

    @property
    def recovered_effect(self) -> float:
        return self.patched_metric - self.corrupted_metric

    @property
    def recovery_fraction(self) -> float | None:
        denominator = self.recoverable_effect
        return self.recovered_effect / denominator if denominator != 0.0 else None


@dataclass(frozen=True)
class PathPatchReport:
    source_node: str
    mediator_node: str
    target_node: str
    observation_count: int
    mean_recoverable_effect: float
    mean_recovered_effect: float
    mean_recovery_fraction: float | None
    positive_recovery_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_node": self.source_node,
            "mediator_node": self.mediator_node,
            "target_node": self.target_node,
            "observation_count": self.observation_count,
            "mean_recoverable_effect": self.mean_recoverable_effect,
            "mean_recovered_effect": self.mean_recovered_effect,
            "mean_recovery_fraction": self.mean_recovery_fraction,
            "positive_recovery_ratio": self.positive_recovery_ratio,
            "digest": self.digest,
        }


def analyze_path_patching(
    observations: Sequence[PathPatchObservation],
) -> tuple[PathPatchReport, ...]:
    if not observations:
        raise ReverseEngineeringError("path patching requires observations")
    grouped: dict[tuple[str, str, str], list[PathPatchObservation]] = {}
    for item in observations:
        grouped.setdefault(
            (item.source_node, item.mediator_node, item.target_node), []
        ).append(item)

    reports: list[PathPatchReport] = []
    for (source, mediator, target), items in sorted(grouped.items()):
        probe_digests = {item.probe_digest for item in items}
        if len(probe_digests) != 1:
            raise ReverseEngineeringError("path-patch group must share probe_digest")
        fractions = [
            item.recovery_fraction for item in items if item.recovery_fraction is not None
        ]
        payload = {
            "probe_digest": next(iter(probe_digests)),
            "source_node": source,
            "mediator_node": mediator,
            "target_node": target,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "clean_metric": item.clean_metric,
                    "corrupted_metric": item.corrupted_metric,
                    "patched_metric": item.patched_metric,
                }
                for item in sorted(items, key=lambda value: value.observation_id)
            ],
        }
        reports.append(
            PathPatchReport(
                source_node=source,
                mediator_node=mediator,
                target_node=target,
                observation_count=len(items),
                mean_recoverable_effect=sum(item.recoverable_effect for item in items) / len(items),
                mean_recovered_effect=sum(item.recovered_effect for item in items) / len(items),
                mean_recovery_fraction=(sum(fractions) / len(fractions) if fractions else None),
                positive_recovery_ratio=sum(item.recovered_effect > 0.0 for item in items) / len(items),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
