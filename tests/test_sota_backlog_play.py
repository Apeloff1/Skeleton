from __future__ import annotations

from skeleton.game.backlog_play import play


def test_backlog_play_seals() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["extract_count"] in {0, 1}
    assert left["sota_ready"] is False
    assert left["packs"] >= 20
