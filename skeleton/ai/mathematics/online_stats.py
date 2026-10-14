"""Mergeable streaming moment and covariance reference summaries."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from .contracts import MathInvariantError, finite_scalar


@dataclass(frozen=True, slots=True)
class RunningMoments:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def update(self, value: Real) -> "RunningMoments":
        x = finite_scalar("value", value)
        count = self.count + 1
        delta = x - self.mean
        mean = self.mean + delta / count
        m2 = self.m2 + delta * (x - mean)
        return RunningMoments(
            count=count,
            mean=mean,
            m2=m2,
            minimum=x if self.minimum is None else min(self.minimum, x),
            maximum=x if self.maximum is None else max(self.maximum, x),
        )

    def merge(self, other: "RunningMoments") -> "RunningMoments":
        if other.count == 0:
            return self
        if self.count == 0:
            return other
        total = self.count + other.count
        delta = other.mean - self.mean
        mean = self.mean + delta * other.count / total
        m2 = (
            self.m2
            + other.m2
            + delta * delta * self.count * other.count / total
        )
        return RunningMoments(
            count=total,
            mean=mean,
            m2=m2,
            minimum=min(self.minimum, other.minimum),  # type: ignore[arg-type]
            maximum=max(self.maximum, other.maximum),  # type: ignore[arg-type]
        )

    def variance(self, *, sample: bool = True) -> float:
        minimum_count = 2 if sample else 1
        if self.count < minimum_count:
            raise MathInvariantError(
                "insufficient observations for requested variance",
                reason="insufficient_observations",
                field="count",
            )
        denominator = self.count - 1 if sample else self.count
        value = self.m2 / denominator
        if value < 0.0 and abs(value) <= 1e-15:
            return 0.0
        return finite_scalar("variance", value)

    def standard_deviation(self, *, sample: bool = True) -> float:
        return math.sqrt(self.variance(sample=sample))


@dataclass(frozen=True, slots=True)
class RunningCovariance:
    count: int = 0
    mean_x: float = 0.0
    mean_y: float = 0.0
    c2: float = 0.0
    m2_x: float = 0.0
    m2_y: float = 0.0

    def update(self, x_value: Real, y_value: Real) -> "RunningCovariance":
        x = finite_scalar("x_value", x_value)
        y = finite_scalar("y_value", y_value)
        count = self.count + 1
        dx = x - self.mean_x
        dy = y - self.mean_y
        mean_x = self.mean_x + dx / count
        mean_y = self.mean_y + dy / count
        return RunningCovariance(
            count=count,
            mean_x=mean_x,
            mean_y=mean_y,
            c2=self.c2 + dx * (y - mean_y),
            m2_x=self.m2_x + dx * (x - mean_x),
            m2_y=self.m2_y + dy * (y - mean_y),
        )

    def merge(self, other: "RunningCovariance") -> "RunningCovariance":
        if other.count == 0:
            return self
        if self.count == 0:
            return other
        total = self.count + other.count
        dx = other.mean_x - self.mean_x
        dy = other.mean_y - self.mean_y
        cross = self.count * other.count / total
        return RunningCovariance(
            count=total,
            mean_x=self.mean_x + dx * other.count / total,
            mean_y=self.mean_y + dy * other.count / total,
            c2=self.c2 + other.c2 + dx * dy * cross,
            m2_x=self.m2_x + other.m2_x + dx * dx * cross,
            m2_y=self.m2_y + other.m2_y + dy * dy * cross,
        )

    def covariance(self, *, sample: bool = True) -> float:
        minimum_count = 2 if sample else 1
        if self.count < minimum_count:
            raise MathInvariantError(
                "insufficient observations for requested covariance",
                reason="insufficient_observations",
                field="count",
            )
        denominator = self.count - 1 if sample else self.count
        return finite_scalar("covariance", self.c2 / denominator)

    def correlation(self) -> float:
        if self.count < 2:
            raise MathInvariantError(
                "correlation requires at least two observations",
                reason="insufficient_observations",
                field="count",
            )
        denominator = math.sqrt(self.m2_x * self.m2_y)
        if denominator == 0.0:
            raise MathInvariantError(
                "correlation is undefined for zero-variance streams",
                reason="zero_variance",
                field="stream",
            )
        return max(-1.0, min(1.0, self.c2 / denominator))
