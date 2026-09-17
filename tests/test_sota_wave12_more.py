from __future__ import annotations

from skeleton.game.wave12_more import play


def test_wave12_more() -> None:
    card = play(seed=8847291)
    assert card["cask"] == 1
    assert card["sota_ready"] is False
