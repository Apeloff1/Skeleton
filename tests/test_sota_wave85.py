from __future__ import annotations

from skeleton.game.wave85_more import play as more
from skeleton.game.wave85_play import play


def test_wave85_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["latched"] == 1
    assert left["sota_ready"] is False


def test_wave85_more() -> None:
    card = more(seed=8847291)
    assert card["open"] == 1
    assert card["sota_ready"] is False
