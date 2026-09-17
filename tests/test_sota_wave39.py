from __future__ import annotations

from skeleton.game.wave39_more import play as more
from skeleton.game.wave39_play import play


def test_wave39_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["deg"] == 45
    assert left["sota_ready"] is False


def test_wave39_more() -> None:
    card = more(seed=8847291)
    assert card["fath"] == 8
    assert card["sota_ready"] is False
