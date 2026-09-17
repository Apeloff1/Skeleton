from __future__ import annotations

from skeleton.game.wave47_more import play as more
from skeleton.game.wave47_play import play


def test_wave47_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["water"] == 3
    assert left["sota_ready"] is False


def test_wave47_more() -> None:
    card = more(seed=8847291)
    assert card["water"] == 2
    assert card["sota_ready"] is False
