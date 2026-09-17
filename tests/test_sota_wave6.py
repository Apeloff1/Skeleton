from __future__ import annotations

from skeleton.game.wave6_play import play


def test_wave6_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["packs"] >= 28
    assert left["sota_ready"] is False
