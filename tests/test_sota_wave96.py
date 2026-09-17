from __future__ import annotations

from skeleton.game.wave96_more import play as more
from skeleton.game.wave96_play import play


def test_wave96_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["st"] == 2
    assert left["sota_ready"] is False


def test_wave96_more() -> None:
    card = more(seed=8847291)
    assert card["cwt"] == 2
    assert card["sota_ready"] is False
