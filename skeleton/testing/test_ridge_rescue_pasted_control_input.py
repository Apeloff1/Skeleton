"""Pasted control characters must never authorize a saved gameplay turn."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("pasted", ["0\\n", "\\n0", "\\t0", "0\\r", "0\\t", "\\x1b0", "0\\x7f"])
def test_control_bearing_input_does_not_commit_a_turn(tmp_path, pasted):
    root = tmp_path / "saves"
    store = SlotStore(root)
    commands = iter([pasted, "q"])
    output = []
    result = play(store, "journey", read=lambda _: next(commands), write=output.append)
    authoritative = SlotStore(root).load("journey")
    assert result["revision"] == authoritative["revision"] == 0
    assert result["head"] == authoritative["head"]
    assert store.audit("journey")["audit_entries"] == 0
    assert any("no turn was consumed" in line for line in output)


def test_plain_ascii_menu_selection_remains_playable(tmp_path):
    store = SlotStore(tmp_path / "saves")
    commands = iter(["0", "q"])
    result = play(store, "journey", read=lambda _: next(commands), write=lambda _: None)
    assert result["revision"] == 1
    assert store.audit("journey")["audit_entries"] == 1
