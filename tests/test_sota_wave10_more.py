from __future__ import annotations

from skeleton.game.wave10_more import play


def test_wave10_more() -> None:
    card = play(seed=8847291)
    assert card["bind"] == 1
    assert card["hold"] == 1
    assert card["sota_ready"] is False
