from __future__ import annotations

from skeleton.game.wave55_more import play as more
from skeleton.game.wave55_play import play


def test_wave55_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["prop"] == 1
    assert left["sota_ready"] is False


def test_wave55_more() -> None:
    card = more(seed=8847291)
    assert card["saggar"] == "sg_01"
    assert card["sota_ready"] is False
