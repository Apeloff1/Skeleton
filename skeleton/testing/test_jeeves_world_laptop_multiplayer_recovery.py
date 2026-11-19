"""End-to-end isolation of two original lighthouse players and portable recovery.

This covers a real reviewed canonical source, builder handoff, independent
branch consequences, and deterministic save restoration without mutation.
"""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.world_canon import CanonError, canonical, digest
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def _files(root):
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_two_players_have_independent_replay_and_portable_recovery(tmp_path):
    flow, proposed, reviewed, receipt = ready(tmp_path)
    assert proposed["review_required"] is True
    assert reviewed["source_digest"] == receipt["source_digest"]
    assert flow.verify("lighthouse") == receipt

    alice = flow.create_session("lighthouse", "alice")
    bob = flow.create_session("lighthouse", "bob")
    alice_next = flow.choose("lighthouse", "alice", "rescue", alice["session_digest"])
    assert alice_next["scene"]["id"] == "shelter"
    assert flow.inspect_session("lighthouse", "bob")["session_digest"] == bob["session_digest"]

    alice_export = flow.export_session("lighthouse", "alice")
    bob_export = flow.export_session("lighthouse", "bob")
    assert alice_export["session"]["scene"] != bob_export["session"]["scene"]
    before = _files(tmp_path)
    alice_preview = flow.preflight_restore("lighthouse", alice_export)
    bob_preview = flow.preflight_restore("lighthouse", bob_export)
    assert alice_preview["restorable"] is True
    assert bob_preview["restorable"] is True
    assert _files(tmp_path) == before

    restored_alice = flow.create_session("lighthouse", "alice-copy", imported=alice_export)
    restored_bob = flow.create_session("lighthouse", "bob-copy", imported=bob_export)
    assert restored_alice["session_digest"] == alice_next["session_digest"]
    assert restored_bob["session_digest"] == bob["session_digest"]
    assert flow.verify("lighthouse") == receipt
    assert not (tmp_path / "lighthouse.lock").exists()


def test_rejected_cross_player_restore_cannot_overwrite_existing_slot(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "player")
    flow.choose("lighthouse", "player", "rescue", first["session_digest"])
    exported = flow.export_session("lighthouse", "player")
    existing = tmp_path / "lighthouse.player.session.json"
    before = existing.read_bytes()

    with pytest.raises(CanonError) as error:
        flow.create_session("lighthouse", "player", imported=exported)
    assert error.value.code == "session_already_exists"
    assert existing.read_bytes() == before
    assert not (tmp_path / "lighthouse.lock").exists()


def test_reviewed_source_change_invalidates_both_player_exports(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "alice")
    flow.create_session("lighthouse", "bob")
    exports = [flow.export_session("lighthouse", slot) for slot in ("alice", "bob")]
    slots = {slot: (tmp_path / f"lighthouse.{slot}.session.json").read_bytes()
             for slot in ("alice", "bob")}
    world = flow.worlds.read("lighthouse")
    changed = dict(world)
    changed["prompt"] = world["prompt"] + " changed after player exports"
    flow.worlds.publish(changed, expected_digest=digest(world))

    for exported in exports:
        with pytest.raises(CanonError) as error:
            flow.preflight_restore("lighthouse", exported)
        assert error.value.code == "review_stale_source"
    for slot, saved in slots.items():
        assert (tmp_path / f"lighthouse.{slot}.session.json").read_bytes() == saved
    assert not (tmp_path / "lighthouse.lock").exists()
