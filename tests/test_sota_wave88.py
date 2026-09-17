from __future__ import annotations

from skeleton.game.wave88_more import play as more
from skeleton.game.wave88_play import play


def test_wave88_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["cool"] == 4
    assert left["sota_ready"] is False


def test_wave88_more() -> None:
    card = more(seed=8847291)
    assert card["settle"] == "se_01"
    assert card["sota_ready"] is False
