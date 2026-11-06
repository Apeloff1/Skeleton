"""Interactive consumer acceptance across malformed input and durable restart.

These host-neutral tests validate the real save adapter and terminal command
boundary; they are not Windows device or installer qualification.
"""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("invalid", [
    "not-a-command",
    "99999999",
    "0\x00",
    "\x1b[31m0",
    "０",
    "١",
    "²",
    "0\n1",
    "0\t1",
    "9" * 129,
])
def test_rejected_interactive_command_cannot_commit_or_corrupt_save(tmp_path, invalid):
    root = tmp_path / "private"
    store = SlotStore(root)
    initial = store.new("adventure")
    messages = []
    answers = iter((invalid, "q"))
    final = play(store, "adventure", read=lambda _: next(answers),
                 write=messages.append, ascii_mode=True)
    cold = SlotStore(root)
    reopened = cold.load("adventure")
    assert final["head"] == reopened["head"] == initial["head"]
    assert final["revision"] == reopened["revision"] == 0
    assert cold.audit("adventure")["verified"] is True
    assert cold.audit("adventure")["audit_entries"] == 0
    assert any("no turn was consumed" in line for line in messages)


def test_restart_after_committed_action_then_invalid_input(tmp_path):
    root = tmp_path / "private"
    store = SlotStore(root)
    initial = store.new("adventure")
    assert initial["actions"]
    output = []
    answers = iter(("0", "not-a-command", "q"))
    first = play(store, "adventure", read=lambda _: next(answers),
                 write=output.append, ascii_mode=True)
    assert first["revision"] == 1
    cold = SlotStore(root)
    reopened = cold.load("adventure")
    assert reopened["head"] == first["head"]
    assert reopened["revision"] == 1
    audit = cold.audit("adventure")
    assert audit["verified"] is True
    assert audit["audit_entries"] == 1
    assert any("no turn was consumed" in line for line in output)


def test_eof_after_first_commit_is_safe_restart(tmp_path):
    root = tmp_path / "private"
    first_store = SlotStore(root)
    initial = first_store.new("adventure")
    assert initial["actions"]
    commands = iter(("0",))
    final = play(first_store, "adventure", read=lambda _: next(commands),
                 write=lambda _: None, ascii_mode=True)
    assert final["revision"] == 1
    cold = SlotStore(root)
    assert cold.load("adventure")["head"] == final["head"]
    assert cold.audit("adventure")["audit_entries"] == 1
