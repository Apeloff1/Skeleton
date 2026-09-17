from __future__ import annotations

from skeleton.game.wave5_more import play


def test_wave5_more() -> None:
    card = play(seed=8847291)
    assert card["ammo"] == 1
    assert card["rumor"] == 1
    assert card["sota_ready"] is False
