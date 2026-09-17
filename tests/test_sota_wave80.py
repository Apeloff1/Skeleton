from __future__ import annotations

from skeleton.game.wave80_more import play as more
from skeleton.game.wave80_play import play


def test_wave80_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["float"] == 1
    assert left["sota_ready"] is False


def test_wave80_more() -> None:
    card = more(seed=8847291)
    assert card["size"] == 2
    assert card["sota_ready"] is False
