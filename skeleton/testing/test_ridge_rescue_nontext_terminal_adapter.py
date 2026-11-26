"""Malformed terminal adapters must exit rather than loop or mutate gameplay."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("invalid", [None, b"0", 0, False, [], {}, object()])
def test_non_text_input_fails_closed_without_busy_loop(tmp_path, invalid):
    root = tmp_path / "saves"
    store = SlotStore(root)
    initial = store.new("journey")
    calls = []
    output = []

    def read(_prompt):
        calls.append(1)
        if len(calls) > 1:
            pytest.fail("non-text input caused an unbounded prompt loop")
        return invalid

    finished = play(store, "journey", read=read, write=output.append)
    reopened = SlotStore(root).load("journey")
    assert len(calls) == 1
    assert finished["head"] == reopened["head"] == initial["head"]
    assert finished["revision"] == 0
    assert store.audit("journey")["audit_entries"] == 0
    assert any("Input stream unavailable" in message for message in output)


def test_non_text_input_after_commit_preserves_replay(tmp_path):
    root = tmp_path / "saves"
    store = SlotStore(root)
    responses = iter(["0", None])
    finished = play(store, "journey", read=lambda _: next(responses), write=lambda _: None)
    reopened = SlotStore(root).load("journey")
    assert finished["revision"] == reopened["revision"] == 1
    assert finished["head"] == reopened["head"]
    assert store.audit("journey")["audit_entries"] == 1
