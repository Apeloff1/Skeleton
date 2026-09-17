from __future__ import annotations

from skeleton.game.wave23_more import play as more
from skeleton.game.wave23_play import play


def test_wave23_play() -> None:
    left = play(seed=8847291, digest="abc")
    right = play(seed=8847291, digest="abc")
    assert left["digest"] == right["digest"]
    assert left["proof"] == 1
    assert left["sota_ready"] is False


def test_wave23_more() -> None:
    card = more(seed=8847291, digest="abc")
    assert card["type"] == 1
    assert card["sota_ready"] is False
