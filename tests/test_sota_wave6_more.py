from __future__ import annotations

from skeleton.game.wave6_more import play


def test_wave6_more() -> None:
    card = play(seed=8847291)
    assert card["badge"] == 1
    assert card["cache"] == 2
    assert card["sota_ready"] is False
