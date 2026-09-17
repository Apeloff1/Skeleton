from __future__ import annotations

from skeleton.game.wave66_more import play as more
from skeleton.game.wave66_play import play


def test_wave66_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["loss"] == 1
    assert left["sota_ready"] is False


def test_wave66_more() -> None:
    card = more(seed=8847291)
    assert card["grain"] == 4
    assert card["sota_ready"] is False
