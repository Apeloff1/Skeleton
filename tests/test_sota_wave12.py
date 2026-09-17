from __future__ import annotations

from skeleton.game.wave12_play import play


def test_wave12_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["graft"] == 1
    assert left["sota_ready"] is False
