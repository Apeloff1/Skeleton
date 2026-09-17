from __future__ import annotations

from skeleton.game.wave16_more import play as more
from skeleton.game.wave16_play import play


def test_wave16_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["water"] >= 1
    assert left["sota_ready"] is False


def test_wave16_more() -> None:
    card = more(seed=8847291)
    assert card["level"] == 6
    assert card["sota_ready"] is False
