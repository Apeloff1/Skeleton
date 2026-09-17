from __future__ import annotations

from skeleton.game.wave34_more import play as more
from skeleton.game.wave34_play import play


def test_wave34_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["tile"] == 1
    assert left["sota_ready"] is False


def test_wave34_more() -> None:
    card = more(seed=8847291)
    assert card["batten"] == 1
    assert card["sota_ready"] is False
