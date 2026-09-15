from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from typing import Iterable

from .gate import PromotionResult, PromotionSignals, evaluate
from .models import AbsorbItem
from .priority import AbsorbSignals, score


@dataclass(frozen=True)
class ScheduledItem:
    item: AbsorbItem
    signals: AbsorbSignals
    promotion: PromotionSignals


class AbsorbScheduler:
    def __init__(self) -> None:
        self._heap: list[tuple[float, int, ScheduledItem]] = []
        self._sequence = count()

    def push(self, scheduled: ScheduledItem) -> float:
        priority = score(scheduled.signals)
        heappush(self._heap, (-priority, next(self._sequence), scheduled))
        return priority

    def extend(self, items: Iterable[ScheduledItem]) -> None:
        for item in items:
            self.push(item)

    def pop(self) -> ScheduledItem:
        if not self._heap:
            raise IndexError("absorb scheduler is empty")
        return heappop(self._heap)[2]

    def __len__(self) -> int:
        return len(self._heap)


def can_promote(item: ScheduledItem) -> PromotionResult:
    return evaluate(item.promotion)
