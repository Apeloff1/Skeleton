from __future__ import annotations

from skeleton.game.wave94_more import play as more
from skeleton.game.wave94_play import play


def test_wave94_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["yd"] == 3
    assert left["sota_ready"] is False


def test_wave94_more() -> None:
    card = more(seed=8847291)
    assert card["rd"] == 2
    assert card["sota_ready"] is False
