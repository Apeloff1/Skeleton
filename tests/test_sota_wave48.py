from __future__ import annotations

from skeleton.game.wave48_more import play as more
from skeleton.game.wave48_play import play


def test_wave48_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["light"] == 1
    assert left["sota_ready"] is False


def test_wave48_more() -> None:
    card = more(seed=8847291)
    assert card["oil"] == 2
    assert card["sota_ready"] is False
