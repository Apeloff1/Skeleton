"""A struggled review is due sooner than a clean recall, without growing ease."""

import math

import pytest

from skeleton.memory.repetition import Outcome, RepetitionScheduler


def test_struggled_interval_is_sooner_than_recall() -> None:
    now = {"t": 1_000_000.0}

    def clock() -> float:
        return now["t"]

    recalled = RepetitionScheduler(clock=clock)
    struggled = RepetitionScheduler(clock=clock)
    recalled.enroll("ep")
    struggled.enroll("ep")
    now["t"] += 10
    clean = recalled.review("ep", Outcome.RECALLED)
    hard = struggled.review("ep", Outcome.STRUGGLED)
    base = -math.log(0.5) * 3600.0
    assert hard.next_due - now["t"] == pytest.approx(base * 0.5)
    assert clean.next_due - now["t"] == pytest.approx(base * clean.ease)
    assert hard.next_due < clean.next_due
    assert hard.stability == 3600.0
    assert hard.ease == 1.0
    assert clean.ease > hard.ease
