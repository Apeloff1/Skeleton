from __future__ import annotations

from skeleton.game.wave7_more import play


def test_wave7_more() -> None:
    card = play(seed=8847291, digest="abc")
    assert card["evidence"] == 1
    assert card["form"] == 1
    assert card["sota_ready"] is False
