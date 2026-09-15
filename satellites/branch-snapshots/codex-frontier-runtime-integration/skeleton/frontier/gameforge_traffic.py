"""Provider-neutral traffic shaping contract mined from GameForge gf-services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrafficClass(str, Enum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"
    BULK = "bulk"


@dataclass(frozen=True)
class TrafficDecision:
    admitted: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.admitted, bool):
            raise TypeError("admitted must be bool")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("reason must be a non-empty string")


class TrafficShaper:
    """Deterministic bounded admission policy for three traffic classes."""

    def __init__(self, interactive: int = 8, background: int = 4, bulk: int = 2) -> None:
        limits = (interactive, background, bulk)
        if any(not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 for limit in limits):
            raise ValueError("traffic limits must be >= 1")
        self._limits = {
            TrafficClass.INTERACTIVE: interactive,
            TrafficClass.BACKGROUND: background,
            TrafficClass.BULK: bulk,
        }
        self._active = {traffic_class: 0 for traffic_class in TrafficClass}

    @staticmethod
    def _validate_class(traffic_class: TrafficClass) -> None:
        if not isinstance(traffic_class, TrafficClass):
            raise TypeError("traffic_class must be a TrafficClass")

    def acquire(self, traffic_class: TrafficClass) -> TrafficDecision:
        self._validate_class(traffic_class)
        active = self._active[traffic_class]
        if active >= self._limits[traffic_class]:
            return TrafficDecision(False, "class_limit")
        self._active[traffic_class] = active + 1
        return TrafficDecision(True, "admitted")

    def release(self, traffic_class: TrafficClass) -> None:
        self._validate_class(traffic_class)
        active = self._active[traffic_class]
        if active <= 0:
            raise ValueError("cannot release an inactive traffic class")
        self._active[traffic_class] = active - 1

    def active(self, traffic_class: TrafficClass) -> int:
        self._validate_class(traffic_class)
        return self._active[traffic_class]

    def remaining(self, traffic_class: TrafficClass) -> int:
        self._validate_class(traffic_class)
        return self._limits[traffic_class] - self._active[traffic_class]

    def saturated(self, traffic_class: TrafficClass) -> bool:
        self._validate_class(traffic_class)
        return self._active[traffic_class] >= self._limits[traffic_class]

    def limit(self, traffic_class: TrafficClass) -> int:
        self._validate_class(traffic_class)
        return self._limits[traffic_class]
