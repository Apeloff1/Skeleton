from __future__ import annotations

from skeleton.game.wave49_more import play as more
from skeleton.game.wave49_play import play


def test_wave49_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["up"] == 1
    assert left["sota_ready"] is False


def test_wave49_more() -> None:
    card = more(seed=8847291)
    assert card["span"] == 6
    assert card["sota_ready"] is False
