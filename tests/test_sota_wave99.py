from __future__ import annotations

from skeleton.game.wave99_more import play as more
from skeleton.game.wave99_play import play


def test_wave99_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["heads"] == 40
    assert left["sota_ready"] is False


def test_wave99_more() -> None:
    card = more(seed=8847291)
    assert card["due"] == 1
    assert card["sota_ready"] is False
