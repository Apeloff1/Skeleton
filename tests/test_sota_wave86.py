from __future__ import annotations

from skeleton.game.wave86_more import play as more
from skeleton.game.wave86_play import play


def test_wave86_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["mi"] == 8
    assert left["sota_ready"] is False


def test_wave86_more() -> None:
    card = more(seed=8847291)
    assert card["cairn"] == "cn_01"
    assert card["sota_ready"] is False
