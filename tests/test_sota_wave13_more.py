from __future__ import annotations

from skeleton.game.wave13_more import play


def test_wave13_more() -> None:
    card = play(seed=8847291)
    assert card["frame"] == 1
    assert card["honey"] == 1
    assert card["sota_ready"] is False
