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


class TrafficShaper:
    """Deterministic bounded admission policy for three traffic classes."""

    def __init__(self, interactive: int = 8, background: int = 4, bulk: int = 2) -> None:
        limits = (interactive, background, bulk)
        if any(limit < 1 for limit in limits):
            raise ValueError("traffic limits must be >= 1")
        self._limits = {
            TrafficClass.INTERACTIVE: interactive,
            TrafficClass.BACKGROUND: background,
            TrafficClass.BULK: bulk,
        }
        self._active = {traffic_class: 0 for traffic_class in TrafficClass}

    def acquire(self, traffic_class: TrafficClass) -> TrafficDecision:
        active = self._active[traffic_class]
        if active >= self._limits[traffic_class]:
            return TrafficDecision(False, "class_limit")
        self._active[traffic_class] = active + 1
        return TrafficDecision(True, "admitted")

    def release(self, traffic_class: TrafficClass) -> None:
        active = self._active[traffic_class]
        if active <= 0:
            raise ValueError("cannot release an inactive traffic class")
        self._active[traffic_class] = active - 1

    def active(self, traffic_class: TrafficClass) -> int:
        return self._active[traffic_class]
