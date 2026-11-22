"""A concurrent first-launch slot creator must not crash or erase progress."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_two_first_launchers_attach_to_authoritative_save(tmp_path, monkeypatch):
    root = tmp_path / "saves"
    first = SlotStore(root)
    second = SlotStore(root)
    real_new = first.new
    raced = {}

    def concurrent_new(name):
        # Another process wins the first-launch create race and commits a
        # valid action before the original creator can insert its slot.
        initial = second.new(name)
        raced["saved"] = second.step(
            name, initial["actions"][0], expected_head=initial["head"]
        )
        return real_new(name)

    monkeypatch.setattr(first, "new", concurrent_new)
    displayed = []
    resumed = play(first, "journey", read=lambda _: "q", write=displayed.append)
    assert resumed["head"] == raced["saved"]["head"]
    assert resumed["revision"] == 1
    assert SlotStore(root).audit("journey")["verified"] is True
    assert any("Revision: 1" in line for line in displayed)


def test_unrelated_create_error_stays_fail_closed(tmp_path, monkeypatch):
    from skeleton.game.gameplay.ridge_rescue.consumer_store import StoreError
    import pytest

    store = SlotStore(tmp_path / "saves")

    def refuse(_name):
        raise StoreError("save slot capacity exhausted")

    monkeypatch.setattr(store, "new", refuse)
    with pytest.raises(StoreError, match="capacity exhausted"):
        play(store, "journey", read=lambda _: "q")
