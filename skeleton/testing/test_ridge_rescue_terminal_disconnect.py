"""Disconnected console input must preserve the authoritative campaign save."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("failure", [OSError("console disconnected"),
                                      UnicodeDecodeError("utf-8", b"\\xff", 0, 1, "bad input")])
def test_terminal_failure_after_committed_turn_quits_without_rollback(tmp_path, failure):
    root = tmp_path / "saves"
    store = SlotStore(root)
    messages = []
    calls = iter(["0", failure])

    def read(_prompt):
        item = next(calls)
        if isinstance(item, BaseException):
            raise item
        return item

    result = play(store, "journey", read=read, write=messages.append)
    reopened = SlotStore(root).load("journey")
    assert result["revision"] == reopened["revision"] == 1
    assert result["head"] == reopened["head"]
    assert SlotStore(root).audit("journey")["audit_entries"] == 1


@pytest.mark.parametrize("failure", [OSError("closed"), UnicodeError("decoder failed")])
def test_terminal_failure_before_first_turn_does_not_mutate(tmp_path, failure):
    store = SlotStore(tmp_path / "saves")

    def read(_prompt):
        raise failure

    result = play(store, "journey", read=read, write=lambda _: None)
    assert result["revision"] == 0
    assert store.audit("journey")["audit_entries"] == 0
