from __future__ import annotations

from skeleton.game.wave29_more import play as more
from skeleton.game.wave29_play import play


def test_wave29_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["wick"] == 1
    assert left["sota_ready"] is False


def test_wave29_more() -> None:
    card = more(seed=8847291)
    assert card["light"] == 1
    assert card["sota_ready"] is False
