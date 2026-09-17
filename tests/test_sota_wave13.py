from __future__ import annotations

from skeleton.game.wave13_play import play


def test_wave13_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["comb"] == 1
    assert left["sota_ready"] is False
