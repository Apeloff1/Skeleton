"""Adversarial replay migration, operator lease and CLI acceptance fixtures."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.migration import MigrationStore, preview_migration
from skeleton.jeeves.worlds.migration_cli import run
from skeleton.jeeves.worlds.session import (
    SessionStore, apply_choice, export_session, new_session,
)
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


def old_world():
    world = propose(world_id="tides", premise="A courier crosses the tide.",
                    protagonist="Iona", region="Estuary", goal="Save the archive.")
    world["scenes"].insert(1, {"id": "pier", "title": "Pier",
                               "narrative": "The pier is silent."})
    world["choices"] = [
        {"id": "board", "from": "opening", "to": "pier",
         "label": "Board", "requires": [], "grants": ["ticket"]},
        {"id": "deliver", "from": "pier", "to": "resolution",
         "label": "Deliver", "requires": ["ticket"], "grants": []},
    ]
    prove(world)
    return world


def checkpoint(world, trace=("board",)):
    state = new_session(world)
    for choice_id in trace:
        state = apply_choice(state, world, choice_id)
    return export_session(state, world)


def revised(world, rename=False):
    target = copy.deepcopy(world)
    target["scenes"][0]["narrative"] = "The tide has risen."
    if rename:
        target["choices"][0]["id"] = "embark"
        target["choices"][0]["label"] = "Embark"
    prove(target)
    return target


def test_preview_proves_earned_state_and_is_deterministic():
    old = old_world()
    new = revised(old)
    save = checkpoint(old)
    before = copy.deepcopy(save)
    first = preview_migration(old, save, new, {})
    assert first == preview_migration(copy.deepcopy(old), save, new, {})
    assert save == before
    assert first["scene"] == "pier"
    assert first["flags"] == ["ticket"]
    assert first["old_choices"] == ["board"]
    assert first["new_choices"] == ["board"]
    assert first["target_world_digest"] == digest(new)
    assert first["playable_proof_digest"] == digest(prove(new).as_dict())


def test_explicit_rename_preserves_causal_effects():
    old = old_world()
    new = revised(old, rename=True)
    with pytest.raises(CanonError, match="migration_choice_missing"):
        preview_migration(old, checkpoint(old), new, {})
    preview = preview_migration(old, checkpoint(old), new, {"board": "embark"})
    assert preview["new_choices"] == ["embark"]
    assert preview["flags"] == ["ticket"]


@pytest.mark.parametrize("field,value", [
    ("from", "pier"), ("to", "opening"),
    ("requires", ["ticket"]), ("grants", []),
])
def test_semantic_changes_are_never_silently_migrated(field, value):
    old = old_world()
    new = revised(old)
    new["choices"][0][field] = value
    with pytest.raises(CanonError):
        preview_migration(old, checkpoint(old), new, {})


def test_changed_ending_label_blocks_completed_checkpoint():
    old = old_world()
    new = revised(old)
    new["endings"][0]["label"] = "A different ending"
    with pytest.raises(CanonError, match="migration_replay_diverged"):
        preview_migration(old, checkpoint(old, ("board", "deliver")), new, {})


def test_forged_checkpoint_rejected_even_when_checksum_recomputed():
    old = old_world()
    new = revised(old)
    save = checkpoint(old)
    save["session"]["flags"] = ["unearned"]
    save["checksum_sha256"] = digest({
        "schema": save["schema"], "session": save["session"]})
    with pytest.raises(CanonError, match="session_replay_mismatch"):
        preview_migration(old, save, new, {})


def test_cross_world_or_unchanged_revision_rejected():
    old = old_world()
    with pytest.raises(CanonError, match="migration_revision_unchanged"):
        preview_migration(old, checkpoint(old), old, {})
    other = revised(old)
    other["id"] = "different"
    with pytest.raises(CanonError, match="migration_world_identity_mismatch"):
        preview_migration(old, checkpoint(old), other, {})


def test_mapping_injection_and_collision_rejected():
    old = old_world()
    new = revised(old)
    save = checkpoint(old, ("board", "deliver"))
    with pytest.raises(CanonError, match="migration_unused_mapping"):
        preview_migration(old, save, new, {"never_played": "board"})
    with pytest.raises(CanonError, match="migration_mapping_collision"):
        preview_migration(old, save, new, {"deliver": "board"})


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_operator_lease_new_slot_only_and_resume(tmp_path):
    old = old_world()
    new = revised(old, rename=True)
    WorldStore(tmp_path).publish(new, create=True)
    store = MigrationStore(str(tmp_path))
    save = checkpoint(old)
    mapping = {"board": "embark"}
    preview = store.preview("tides", old, save, mapping)
    lease = digest(preview)
    with pytest.raises(CanonError, match="migration_stale_preview"):
        store.apply("tides", "slot1", old, save, mapping,
                    expected_preview_digest="0" * 64, review_note="Approved.")
    receipt = store.apply("tides", "slot1", old, save, mapping,
                          expected_preview_digest=lease, review_note="Approved.")
    assert receipt["player"]["scene"]["id"] == "pier"
    assert SessionStore(tmp_path).read("tides", "slot1")["choices"] == ["embark"]
    with pytest.raises(CanonError, match="session_already_exists"):
        store.apply("tides", "slot1", old, save, mapping,
                    expected_preview_digest=lease, review_note="Approved.")
    view = SessionStore(tmp_path).inspect("tides", "slot1")
    end = SessionStore(tmp_path).choose(
        "tides", "slot1", "deliver", view["session_digest"])
    assert end["ending"] == "Save the archive."


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_stale_world_lease_and_lock_refusal(tmp_path):
    old = old_world()
    new = revised(old)
    worlds = WorldStore(tmp_path)
    worlds.publish(new, create=True)
    store = MigrationStore(str(tmp_path))
    save = checkpoint(old)
    preview = store.preview("tides", old, save, {})
    latest = copy.deepcopy(new)
    latest["scenes"][0]["title"] = "A revised title"
    worlds.publish(latest, expected_digest=digest(new))
    with pytest.raises(CanonError, match="migration_stale_preview"):
        store.apply("tides", "slot1", old, save, {},
                    expected_preview_digest=digest(preview),
                    review_note="Reviewed.")
    (tmp_path / "tides.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.apply("tides", "slot1", old, save, {},
                    expected_preview_digest=digest(preview),
                    review_note="Reviewed.")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_symlink_slot_refused_without_external_overwrite(tmp_path):
    old = old_world()
    new = revised(old)
    worlds = WorldStore(tmp_path)
    worlds.publish(new, create=True)
    outside = tmp_path.parent / "outside-migration"
    outside.write_text("safe")
    (tmp_path / "tides.slot1.session.json").symlink_to(outside)
    store = MigrationStore(str(tmp_path))
    save = checkpoint(old)
    with pytest.raises((CanonError, OSError)):
        store.apply("tides", "slot1", old, save, {},
                    expected_preview_digest=digest(store.preview("tides", old, save, {})),
                    review_note="Reviewed.")
    assert outside.read_text() == "safe"


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_cli_preview_apply_and_replay(tmp_path, capsys):
    old = old_world()
    new = revised(old)
    WorldStore(tmp_path).publish(new, create=True)
    source_path = tmp_path / "old-world-source.json"
    checkpoint_path = tmp_path / "old-save.json"
    source_path.write_text(json.dumps(old))
    checkpoint_path.write_text(json.dumps(checkpoint(old)))
    args = ["--store", str(tmp_path), "preview", "--world-id", "tides",
            "--old-world-file", str(source_path),
            "--checkpoint-file", str(checkpoint_path)]
    assert run(args) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["preview"]["scene"] == "pier"
    apply_args = args[:2] + ["apply"] + args[3:] + [
        "--slot", "slot1", "--expected-preview-digest",
        response["preview_digest"], "--review-note", "Operator approved."]
    assert run(apply_args) == 0
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert receipt["player"]["flags"] == ["ticket"]


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_symlink_import_file_rejected(tmp_path, capsys):
    old = old_world()
    WorldStore(tmp_path).publish(revised(old), create=True)
    actual = tmp_path / "source.json"
    actual.write_text(json.dumps(old))
    link = tmp_path / "link.json"
    link.symlink_to(actual)
    assert run(["--store", str(tmp_path), "preview", "--world-id", "tides",
                "--old-world-file", str(link),
                "--checkpoint-file", str(actual)]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
