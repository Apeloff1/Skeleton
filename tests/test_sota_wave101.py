from __future__ import annotations

from skeleton.game.wave101_more import play as more
from skeleton.game.wave101_play import play


def test_wave101_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["ruled"] == 1
    assert left["sota_ready"] is False


def test_wave101_more() -> None:
    card = more(seed=8847291)
    assert card["leaves"] == 4
    assert card["sota_ready"] is False
