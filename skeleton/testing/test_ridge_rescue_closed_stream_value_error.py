"""Closed terminal streams must not mutate or erase committed gameplay."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("failure", [
    ValueError("I/O operation on closed file"),
    EOFError(),
    KeyboardInterrupt(),
    StopIteration(),
    OSError("console disconnected"),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
])
def test_closed_stream_preserves_authoritative_save(tmp_path, failure):
    store = SlotStore(tmp_path / "saves")
    original = store.new("journey")

    def closed_stream(_prompt):
        raise failure

    output = []
    finished = play(store, "journey", read=closed_stream, write=output.append)
    reopened = SlotStore(tmp_path / "saves").load("journey")
    assert finished["head"] == original["head"] == reopened["head"]
    assert finished["revision"] == reopened["revision"] == 0
    assert store.audit("journey")["audit_entries"] == 0


def test_closed_stream_after_committed_turn_keeps_progress(tmp_path):
    store = SlotStore(tmp_path / "saves")
    calls = iter(["0", ValueError("closed input stream")])

    def read(_prompt):
        value = next(calls)
        if isinstance(value, BaseException):
            raise value
        return value

    finished = play(store, "journey", read=read, write=lambda _: None)
    reopened = SlotStore(tmp_path / "saves").load("journey")
    assert finished["head"] == reopened["head"]
    assert finished["revision"] == reopened["revision"] == 1
    assert store.audit("journey")["audit_entries"] == 1
