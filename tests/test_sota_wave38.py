from __future__ import annotations

from skeleton.game.wave38_more import play as more
from skeleton.game.wave38_play import play


def test_wave38_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["az"] == 90
    assert left["sota_ready"] is False


def test_wave38_more() -> None:
    card = more(seed=8847291)
    assert card["az"] == 180
    assert card["sota_ready"] is False
