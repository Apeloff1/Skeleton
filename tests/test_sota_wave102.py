from __future__ import annotations

from skeleton.game.wave102_more import play as more
from skeleton.game.wave102_play import play


def test_wave102_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["nib"] == 1
    assert left["sota_ready"] is False


def test_wave102_more() -> None:
    card = more(seed=8847291)
    assert card["ink"] == 1
    assert card["sota_ready"] is False
