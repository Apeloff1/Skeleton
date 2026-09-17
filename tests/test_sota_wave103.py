from __future__ import annotations

from skeleton.game.wave103_more import play as more
from skeleton.game.wave103_play import play


def test_wave103_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["sewn"] == 1
    assert left["sota_ready"] is False


def test_wave103_more() -> None:
    card = more(seed=8847291)
    assert card["headband"] == "hb_01"
    assert card["sota_ready"] is False
