"""Traceable, diagnostic-only project metric observations."""
from __future__ import annotations

from dataclasses import dataclass


class ProjectMetricError(RuntimeError):
    pass


def _text(value: str, field: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 2048:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


@dataclass(frozen=True, slots=True)
class MetricObservation:
    metric_id: str
    category: str
    value: int | float
    source_refs: tuple[str, ...]
    numerator: int | None = None
    denominator: int | None = None
    completion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _text(self.metric_id, "metric_id"))
        if self.category not in {"activity", "throughput", "quality", "risk", "outcome"}:
            raise ValueError("unsupported metric category")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("metric value must be numeric")
        refs = tuple(_text(item, "source_ref") for item in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ValueError("metric requires unique source_refs")
        object.__setattr__(self, "source_refs", refs)
        if self.completion_authority is not False:
            raise ProjectMetricError("project metrics have zero completion authority")
        if (self.numerator is None) != (self.denominator is None):
            raise ValueError("ratio metrics require both numerator and denominator")
        if self.denominator is not None:
            if (
                isinstance(self.numerator, bool)
                or not isinstance(self.numerator, int)
                or self.numerator < 0
                or isinstance(self.denominator, bool)
                or not isinstance(self.denominator, int)
                or self.denominator <= 0
            ):
                raise ValueError("ratio numerator/denominator are invalid")
            if self.numerator > self.denominator:
                raise ValueError("ratio numerator cannot exceed denominator")
            expected = self.numerator / self.denominator
            if abs(float(self.value) - expected) > 1e-12:
                raise ValueError("ratio value does not match numerator/denominator")


def ratio_observation(
    metric_id: str,
    category: str,
    numerator: int,
    denominator: int,
    source_refs: tuple[str, ...],
) -> MetricObservation:
    if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator <= 0:
        raise ProjectMetricError("metric denominator must be positive")
    if isinstance(numerator, bool) or not isinstance(numerator, int) or numerator < 0:
        raise ProjectMetricError("metric numerator must be non-negative")
    return MetricObservation(
        metric_id=metric_id,
        category=category,
        value=numerator / denominator,
        source_refs=source_refs,
        numerator=numerator,
        denominator=denominator,
    )


__all__ = ["MetricObservation", "ProjectMetricError", "ratio_observation"]
