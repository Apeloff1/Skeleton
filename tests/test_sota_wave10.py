from __future__ import annotations

from skeleton.game.wave10_play import play


def test_wave10_play() -> None:
    left = play(seed=8847291, digest="abc")
    right = play(seed=8847291, digest="abc")
    assert left["digest"] == right["digest"]
    assert left["folio"] == 1
    assert left["sota_ready"] is False
