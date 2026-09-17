from __future__ import annotations

from skeleton.game.wave11_more import play


def test_wave11_more() -> None:
    card = play(seed=8847291, digest="abc")
    assert card["chart"] == 1
    assert card["tq"] == 1
    assert card["sota_ready"] is False
