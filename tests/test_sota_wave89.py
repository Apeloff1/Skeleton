from __future__ import annotations

from skeleton.game.wave89_more import play as more
from skeleton.game.wave89_play import play


def test_wave89_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["heard"] == 1
    assert left["sota_ready"] is False


def test_wave89_more() -> None:
    card = more(seed=8847291)
    assert card["marketstall"] == "ms_01"
    assert card["sota_ready"] is False
