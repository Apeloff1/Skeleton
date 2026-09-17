from __future__ import annotations

from skeleton.game.wave84_more import play as more
from skeleton.game.wave84_play import play


def test_wave84_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["slope"] == 6
    assert left["sota_ready"] is False


def test_wave84_more() -> None:
    card = more(seed=8847291)
    assert card["cope"] == "cp_01"
    assert card["sota_ready"] is False
