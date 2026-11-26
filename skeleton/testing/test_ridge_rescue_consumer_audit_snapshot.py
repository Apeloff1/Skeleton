"""Concurrent save audit must replay one transactionally consistent snapshot."""
from __future__ import annotations

from threading import Event, Thread

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_audit_snapshot_remains_valid_during_another_writer(tmp_path, monkeypatch):
    root = tmp_path / "saves"
    store = SlotStore(root)
    initial = store.new("game")
    action = initial["actions"][0]
    started = Event()
    writer_entered = Event()
    errors = []

    def write_next_turn():
        writer_entered.set()
        try:
            SlotStore(root).step("game", action, expected_head=initial["head"])
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=write_next_turn, daemon=True)
    original_read = SlotStore._read

    def hooked_read(conn, name):
        snapshot = original_read(conn, name)
        if not started.is_set():
            started.set()
            worker.start()
            assert writer_entered.wait(timeout=3)
        return snapshot

    monkeypatch.setattr(SlotStore, "_read", staticmethod(hooked_read))
    # The writer may begin while audit holds its read transaction, but it
    # cannot publish a half-old, half-new snapshot into the audit result.
    audit = store.audit("game")
    worker.join(timeout=10)
    assert not worker.is_alive(), "writer did not finish after audit released its snapshot"
    assert not errors
    assert audit["verified"] is True
    assert audit["revision"] == 0
    assert audit["audit_entries"] == 0
    after = store.audit("game")
    assert after["verified"] is True
    assert after["revision"] == 1
    assert after["audit_entries"] == 1
