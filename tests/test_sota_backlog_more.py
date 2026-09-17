from __future__ import annotations

from skeleton.game.backlog_more import play


def test_backlog_more() -> None:
    card = play(seed=8847291, digest="abc")
    assert card["saved"] == 1
    assert card["sota_ready"] is False
