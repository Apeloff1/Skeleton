"""Player choice replay, source leases, portable checkpoint and CLI acceptance."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.session import (
    SessionStore, apply_choice, export_session, import_session, new_session,
    player_view, replay_choices, validate_session,
)
from skeleton.jeeves.worlds.session_cli import run
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    source = propose(
        world_id="marsh", premise="A courier crosses the marsh.",
        protagonist="Iris", region="Marsh", goal="Deliver the letter.",
    )
    source["scenes"].insert(1, {
        "id": "ferry", "title": "Old Ferry", "narrative": "A ferryman waits.",
    })
    source["choices"] = [
        {"id": "board", "from": "opening", "to": "ferry",
         "label": "Board ferry", "requires": [], "grants": ["ticket"]},
        {"id": "deliver", "from": "ferry", "to": "resolution",
         "label": "Deliver letter", "requires": ["ticket"], "grants": []},
    ]
    prove(source)
    return source


def test_new_session_is_playable_and_earned_flags_are_replayed():
    source = world()
    first = new_session(source)
    assert first["scene"] == "opening"
    assert first["revision"] == 0
    assert player_view(first, source)["available_choices"][0]["id"] == "board"
    second = apply_choice(first, source, "board")
    assert second["scene"] == "ferry"
    assert second["flags"] == ["ticket"]
    assert second["revision"] == 1
    third = apply_choice(second, source, "deliver")
    assert third["ending"] == "Deliver the letter."
    assert replay_choices(source, third["choices"])["scene"] == "resolution"
    with pytest.raises(CanonError, match="session_already_ended"):
        apply_choice(third, source, "board")


def test_uneared_choice_and_wrong_scene_fail_closed():
    source = world()
    with pytest.raises(CanonError, match="session_invalid_transition"):
        apply_choice(new_session(source), source, "deliver")
    with pytest.raises(CanonError, match="session_invalid_transition"):
        replay_choices(source, ["missing"])


def test_replay_rejects_forged_flags_and_revision():
    source = world()
    state = apply_choice(new_session(source), source, "board")
    forged = copy.deepcopy(state)
    forged["flags"] = []
    with pytest.raises(CanonError, match="session_replay_mismatch"):
        validate_session(forged, source)
    forged = copy.deepcopy(state)
    forged["revision"] = 99
    with pytest.raises(CanonError, match="session_replay_mismatch"):
        validate_session(forged, source)


def test_replay_rejects_post_ending_extra_steps():
    source = world()
    with pytest.raises(CanonError, match="session_after_ending"):
        replay_choices(source, ["board", "deliver", "board"])


def test_source_lease_rejects_changed_world():
    source = world()
    state = new_session(source)
    source["scenes"][0]["title"] = "Changed"
    with pytest.raises(CanonError, match="session_world_lease_mismatch"):
        validate_session(state, source)


def test_portable_checkpoint_round_trip_and_tamper():
    source = world()
    state = apply_choice(new_session(source), source, "board")
    payload = export_session(state, source)
    assert import_session(payload, source) == state
    assert export_session(import_session(payload, source), source) == payload
    payload["session"]["scene"] = "resolution"
    with pytest.raises(CanonError, match="session_checksum_mismatch"):
        import_session(payload, source)


def test_checksum_is_integrity_not_signature():
    source = world()
    payload = export_session(new_session(source), source)
    assert payload["schema"] == "jeeves.world.session_export.v1"
    assert len(payload["checksum_sha256"]) == 64
    assert "signature" not in payload


def test_canonical_session_is_deterministic_and_pure():
    source = world()
    before = canonical(source)
    state = new_session(source)
    assert canonical(state) == canonical(new_session(copy.deepcopy(source)))
    assert canonical(source) == before


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_persisted_player_replay_and_cas(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = SessionStore(root)
    first = store.create("marsh", "slot1")
    old = first["session_digest"]
    assert first["scene"]["id"] == "opening"
    second = store.choose("marsh", "slot1", "board", old)
    assert second["scene"]["id"] == "ferry"
    with pytest.raises(CanonError, match="stale_session"):
        store.choose("marsh", "slot1", "deliver", old)
    third = store.choose("marsh", "slot1", "deliver", second["session_digest"])
    assert third["ending"] == "Deliver the letter."
    assert store.inspect("marsh", "slot1") == third


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_portable_export_import_creates_new_slot_only(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = SessionStore(root)
    first = store.create("marsh", "original")
    store.choose("marsh", "original", "board", first["session_digest"])
    checkpoint = store.export("marsh", "original")
    recovered = store.create("marsh", "recovered", imported=checkpoint)
    assert recovered["scene"]["id"] == "ferry"
    with pytest.raises(CanonError, match="session_already_exists"):
        store.create("marsh", "recovered", imported=checkpoint)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_stale_world_revision_blocks_saved_game(tmp_path):
    root = tmp_path / "private"
    source = world()
    worlds = WorldStore(root)
    old = worlds.publish(source, create=True)
    SessionStore(root).create("marsh", "slot1")
    updated = copy.deepcopy(source)
    updated["scenes"][0]["title"] = "Revised world"
    worlds.publish(updated, expected_digest=old)
    with pytest.raises(CanonError, match="session_world_lease_mismatch"):
        SessionStore(root).inspect("marsh", "slot1")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_symlinked_session_and_lock_refused(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    outside = tmp_path / "outside"
    outside.write_text(json.dumps(new_session(world())))
    (root / "marsh.slot1.session.json").symlink_to(outside)
    with pytest.raises((CanonError, OSError)):
        SessionStore(root).read("marsh", "slot1")
    (root / "marsh.slot1.session.json").unlink()
    (root / "marsh.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        SessionStore(root).create("marsh", "slot1")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_player_save_export_import_and_resume(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["new", "--world-id", "marsh", "--slot", "slot1"]) == 0
    first = json.loads(capsys.readouterr().out)["player"]
    assert run(args + ["choose", "--world-id", "marsh", "--slot", "slot1",
                       "--choice-id", "board",
                       "--expected-digest", first["session_digest"]]) == 0
    second = json.loads(capsys.readouterr().out)["player"]
    assert second["flags"] == ["ticket"]
    assert run(args + ["export", "--world-id", "marsh", "--slot", "slot1"]) == 0
    checkpoint = json.loads(capsys.readouterr().out)["checkpoint"]
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(checkpoint))
    assert run(args + ["import", "--world-id", "marsh", "--slot", "slot2",
                       "--checkpoint-file", str(path)]) == 0
    restored = json.loads(capsys.readouterr().out)["player"]
    assert restored["session_digest"] == second["session_digest"]
