from __future__ import annotations

from skeleton.game.wave70_more import play as more
from skeleton.game.wave70_play import play


def test_wave70_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["hay"] == 6
    assert left["sota_ready"] is False


def test_wave70_more() -> None:
    card = more(seed=8847291)
    assert card["barnbay"] == "bb_01"
    assert card["sota_ready"] is False
