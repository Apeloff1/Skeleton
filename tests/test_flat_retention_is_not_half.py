"""A review that does not improve is not scored as one half, and it is not perfect."""

import pytest

from skeleton.memory.consolidation import ConsolidationCycle
from skeleton.memory.core import RepetitionScheduler


class _Krem:
    def __init__(self, values):
        self.values = list(values)
        self.observed = 0

    def due(self):
        return ["concept"]

    def retention(self, concept):
        return self.values[min(self.observed, len(self.values) - 1)]

    def observe(self, concept):
        self.observed += 1


class _Scheduler:
    def __init__(self):
        self.performance = None

    def schedule(self, item, interval_hours):
        return None

    def due_items(self):
        return ["krem:concept"]

    def review(self, item, performance):
        self.performance = performance


def test_measured_retention_is_the_review_score() -> None:
    scheduler = _Scheduler()
    cycle = ConsolidationCycle(_Krem([0.2, 0.2]), scheduler)
    cycle.cycle()
    assert scheduler.performance == 0.2
    with pytest.raises(ValueError):
        ConsolidationCycle(_Krem([True, True]), _Scheduler()).cycle()
    repetition = RepetitionScheduler()
    with pytest.raises(KeyError):
        repetition.review("missing", 1.0)
    repetition.schedule("item", interval_hours=24)
    assert repetition.review("item", 0.0) == 12
