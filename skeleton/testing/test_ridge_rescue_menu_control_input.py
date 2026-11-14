"""Menu control characters must never commit an unintended game action."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("bad", ["0\x00", "\x1b0", "0\x7f", "0\ud800", "\x000"])
def test_invisible_or_invalid_input_cannot_commit_a_turn(tmp_path, bad):
    store = SlotStore(tmp_path / "saves")
    messages = []
    choices = iter([bad, "q"])
    result = play(store, "journey", read=lambda _: next(choices), write=messages.append)
    assert result["revision"] == 0
    assert store.audit("journey")["audit_entries"] == 0
    assert any("Unavailable command" in message for message in messages)


def test_normal_numeric_action_still_commits(tmp_path):
    store = SlotStore(tmp_path / "saves")
    choices = iter(["0", "q"])
    result = play(store, "journey", read=lambda _: next(choices), write=lambda _: None)
    assert result["revision"] == 1
    assert store.audit("journey")["verified"]
