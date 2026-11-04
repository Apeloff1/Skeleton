"""Interactive audit proves replay custody without consuming a game turn."""
from pathlib import Path

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_interactive_audit_reports_verified_history_without_mutation(tmp_path: Path):
    store = SlotStore(tmp_path / "save")
    before = store.new("audit")
    messages = []
    commands = iter(("a", "audit", "q"))
    after = play(store, "audit", read=lambda _: next(commands),
                 write=messages.append, ascii_mode=True)
    assert after["head"] == before["head"]
    assert after["revision"] == 0
    reports = [item for item in messages if item.startswith("Save audit verified:")]
    assert len(reports) == 2
    assert all('"verified": true' in item for item in reports)


def test_interactive_audit_detects_newer_authoritative_revision(tmp_path: Path):
    first = SlotStore(tmp_path / "save")
    second = SlotStore(tmp_path / "save")
    before = first.new("audit")
    messages = []
    calls = 0

    def read(_prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            second.step("audit", before["actions"][0], expected_head=before["head"])
            return "a"
        return "q"

    after = play(first, "audit", read=read, write=messages.append, ascii_mode=True)
    assert after["revision"] == 1
    assert any("newer authoritative save" in item for item in messages)
    assert any("Save audit verified:" in item for item in messages)


def test_interactive_audit_failure_does_not_advance_turn(tmp_path: Path, monkeypatch):
    store = SlotStore(tmp_path / "save")
    before = store.new("audit")
    messages = []

    def fail(_slot):
        from skeleton.game.gameplay.ridge_rescue.consumer_store import StoreError
        raise StoreError("audit unavailable")

    monkeypatch.setattr(store, "audit", fail)
    commands = iter(("audit", "q"))
    after = play(store, "audit", read=lambda _: next(commands),
                 write=messages.append, ascii_mode=True)
    assert after["head"] == before["head"]
    assert after["revision"] == 0
    assert any("Save audit unavailable; no turn was consumed" in item for item in messages)
