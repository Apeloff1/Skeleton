from __future__ import annotations

from skeleton.game.wave62_more import play as more
from skeleton.game.wave62_play import play


def test_wave62_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["turn"] == 1
    assert left["sota_ready"] is False


def test_wave62_more() -> None:
    card = more(seed=8847291)
    assert card["ploughshare"] == "ps_01"
    assert card["sota_ready"] is False
