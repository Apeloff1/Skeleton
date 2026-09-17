from __future__ import annotations

from skeleton.game.wave8_more import play


def test_wave8_more() -> None:
    card = play(seed=8847291)
    assert card["ore"] == 1
    assert card["ingot"] == 1
    assert card["sota_ready"] is False
