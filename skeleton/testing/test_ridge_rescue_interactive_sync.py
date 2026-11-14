"""Interactive synchronization reloads authoritative concurrent save without a turn."""
from pathlib import Path

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_sync_refreshes_concurrent_save_without_consuming_turn(tmp_path: Path):
    root = tmp_path / "save"
    first = SlotStore(root)
    other = SlotStore(root)
    initial = first.new("sync")
    messages = []
    calls = 0

    def read(_prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            committed = other.step("sync", initial["actions"][0], expected_head=initial["head"])
            assert committed["revision"] == 1
            return "s"
        if calls == 2:
            return "help"
        return "q"

    result = play(first, "sync", read=read, write=messages.append, ascii_mode=True)
    authoritative = other.load("sync")
    assert result["head"] == authoritative["head"]
    assert result["revision"] == authoritative["revision"] == 1
    assert any("Authoritative save refreshed" in message for message in messages)
    assert all(message.isascii() for message in messages)


def test_sync_does_not_mutate_single_process_save(tmp_path: Path):
    store = SlotStore(tmp_path / "save")
    original = store.new("alone")
    commands = iter(("sync", "s", "q"))
    result = play(store, "alone", read=lambda _: next(commands), write=lambda _: None,
                  ascii_mode=True)
    assert result["head"] == original["head"]
    assert result["revision"] == 0
