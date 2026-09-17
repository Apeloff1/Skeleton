from __future__ import annotations

from skeleton.game.wave9_more import play


def test_wave9_more() -> None:
    card = play(seed=8847291, digest="abc")
    assert card["bolt"] == 1
    assert card["survey"] == 1
    assert card["sota_ready"] is False
