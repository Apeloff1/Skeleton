from __future__ import annotations

from skeleton.game.wave5_play import play


def test_wave5_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["packs"] >= 30
    assert left["sota_ready"] is False
