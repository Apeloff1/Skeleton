"""Canonical source -> offline choice editor -> exported edit -> quest replay."""
from __future__ import annotations

from hashlib import sha256
import io
import json
import os
import zipfile

import pytest

from scripts.studio_choice_rehearsal_cli import main as choice_cli
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_director_choice_rehearsal import (
    EXPORT_FILENAME, EXPORT_SCHEMA, MAX_EXPORT_BYTES, load_choice_export,
    render_choice_rehearsal, replay_choice_export,
)
from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
    compile_director_handoff, publish_director_handoff, verify_director_handoff,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _digest, compile_scene_schedule,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def source():
    documents = read_blueprint(PROJECT)
    canon = audit_canon_source(documents, authorized=True)["source_digest"]
    visual = sha256(json.dumps(
        documents["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    session = replay_quest(documents, [], authorized=True).digest
    scenes = documents["scene"]["episode_plan"]
    schedule = {
        "scene_ticks": {row["id"]: 5 for row in scenes},
        "npc_turnaround_ticks": 2, "min_start_ticks": {},
    }
    recipe = documents["visual"]["asset_recipes"][0]["id"]
    assignments = {
        row["id"]: {
            ref: recipe for ref in row["assets"] + row["interactive_objects"]
        } for row in scenes
    }
    timing = compile_scene_schedule(
        documents, [], schedule, authorized=True,
        expected_source_digest=canon, expected_session_digest=session)
    return documents, canon, visual, session, schedule, assignments, timing


def exported(documents, canon, session, actions=None):
    program = compile_quest_program(documents)
    if actions is None:
        actions = []
    return {
        "schema": EXPORT_SCHEMA, "project_id": program.project_id,
        "source_digest": canon, "quest_source_digest": program.source_digest,
        "base_session_digest": session, "base_actions": [], "actions": actions,
    }


def test_offline_choice_theater_is_in_deterministic_playable_bundle():
    documents, canon, visual, session, schedule, assignments, _ = source()
    kwargs = dict(
        authorized=True, expected_source_digest=canon,
        expected_visual_digest=visual, expected_session_digest=session)
    manifest, bundle = compile_director_handoff(
        documents, [], schedule, assignments, **kwargs)
    second_manifest, second_bundle = compile_director_handoff(
        documents, [], schedule, assignments, **kwargs)
    assert manifest == second_manifest
    assert bundle == second_bundle
    assert manifest["canonical_html5_gameplay_replay_verified"] is True
    assert manifest["offline_choice_rehearsal_receipt"]["browser_export_trusted"] is False
    assert manifest["npc_dialogue_executed_verified"] is False
    assert manifest["release_certified"] is False
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.namelist() == [
            "index.html", "director_editor.html", "choice_rehearsal.html",
            "scene_schedule.json", "scene_asset_bindings.json",
            "director_manifest.json",
        ]
        html = archive.read("choice_rehearsal.html")
        assert b"Original quest choice rehearsal" in html
        assert b"Content-Security-Policy" in html
        assert b"connect-src &#x27;none&#x27;" in html
        assert b"eval(" not in html
        assert b"studio_choice_rehearsal.json" in html
        assert b"choice_rehearsal.html" in archive.read("director_editor.html")
        assert sha256(html).hexdigest() == manifest["file_hashes"]["choice_rehearsal.html"]
        assert sha256(html).hexdigest() == (
            manifest["offline_choice_rehearsal_receipt"]["html_sha256"])


def test_replay_one_authored_choice_and_export_roundtrip(tmp_path, capsys):
    documents, canon, _, session, _, _, _ = source()
    stage = compile_quest_program(documents).stages[0]
    action = [[stage.key, stage.alternatives[0]]]
    export = exported(documents, canon, session, action)
    path = tmp_path / EXPORT_FILENAME
    path.write_text(json.dumps(export), encoding="utf-8")
    assert load_choice_export(path) == export
    result = replay_choice_export(
        documents, load_choice_export(path), authorized=True,
        expected_source_digest=canon, expected_session_digest=session)
    assert result["verified_actions"] == action
    assert result["progress"]["stage_completed"] == 1
    assert result["replay_verified"] is True
    assert result["release_certified"] is False
    assert choice_cli([
        "--project", PROJECT, "--expected-source", canon,
        "--expected-session", session, "--export", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == result


def test_unauthorized_and_stale_source_or_session_fail_closed():
    documents, canon, _, session, _, _, timing = source()
    with pytest.raises(PermissionError):
        render_choice_rehearsal(
            documents, [], timing, authorized=False,
            expected_source_digest=canon)
    with pytest.raises(PermissionError):
        replay_choice_export(
            documents, exported(documents, canon, session),
            authorized=False, expected_source_digest=canon,
            expected_session_digest=session)
    with pytest.raises(StudioQuestError, match="canon"):
        render_choice_rehearsal(
            documents, [], timing, authorized=True,
            expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError, match="lease"):
        replay_choice_export(
            documents, exported(documents, canon, session),
            authorized=True, expected_source_digest=canon,
            expected_session_digest="0" * 64)


def test_edited_schedule_receipt_is_not_authoritative():
    documents, canon, _, _, _, _, timing = source()
    forged = dict(timing)
    forged["timeline"] = [dict(row) for row in timing["timeline"]]
    forged["timeline"][0]["start_tick"] = 999
    with pytest.raises(StudioQuestError, match="schedule lease"):
        render_choice_rehearsal(
            documents, [], forged, authorized=True,
            expected_source_digest=canon)


def test_self_hashed_forgery_cannot_replace_canonical_schedule():
    documents, canon, _, _, _, _, timing = source()
    forged = dict(timing)
    forged["timeline"] = [dict(row) for row in timing["timeline"]]
    forged["timeline"][0]["start_tick"] += 3
    forged["schedule_digest"] = _digest({
        key: value for key, value in forged.items() if key != "schedule_digest"
    })
    with pytest.raises(StudioQuestError, match="canonical schedule proof"):
        render_choice_rehearsal(
            documents, [], forged, authorized=True,
            expected_source_digest=canon)


@pytest.mark.parametrize("mutator", [
    lambda e: {**e, "schema": "unknown"},
    lambda e: {**e, "project_id": "different"},
    lambda e: {**e, "source_digest": "0" * 64},
    lambda e: {**e, "quest_source_digest": "0" * 64},
    lambda e: {**e, "base_session_digest": "0" * 64},
    lambda e: {**e, "unexpected": True},
    lambda e: {**e, "actions": [["forged_stage", "forged_choice"]]},
    lambda e: {**e, "actions": [1]},
    lambda e: {**e, "actions": [["x", "y"]] * 65},
    lambda e: {**e, "base_actions": [["forged", "choice"]]},
    lambda e: {**e, "actions": True},
])
def test_forged_and_unbounded_browser_edits_are_rejected(mutator):
    documents, canon, _, session, _, _, _ = source()
    with pytest.raises((StudioQuestError, TypeError, ValueError)):
        replay_choice_export(
            documents, mutator(exported(documents, canon, session)),
            authorized=True, expected_source_digest=canon,
            expected_session_digest=session)


def test_baseline_cannot_be_rewritten_or_dropped():
    documents, canon, _, session, _, _, _ = source()
    first = compile_quest_program(documents).stages[0]
    first_action = [first.key, first.alternatives[0]]
    base_session = replay_quest(documents, [first_action], authorized=True).digest
    payload = exported(documents, canon, base_session)
    payload["base_actions"] = [first_action]
    payload["actions"] = []
    with pytest.raises(StudioQuestError, match="append-only"):
        replay_choice_export(
            documents, payload, authorized=True,
            expected_source_digest=canon,
            expected_session_digest=base_session)


@pytest.mark.parametrize("raw", [
    b"",
    b'{"schema":',
    b'{"schema":"a","schema":"b"}',
    b'{"schema":NaN}',
    b'{"schema":Infinity}',
    b'["wrong", "root"]',
    b"x" * (MAX_EXPORT_BYTES + 1),
])
def test_import_rejects_malformed_ambiguous_and_oversize(tmp_path, raw):
    path = tmp_path / EXPORT_FILENAME
    path.write_bytes(raw)
    with pytest.raises((StudioQuestError, ValueError)):
        load_choice_export(path)


def test_import_rejects_linked_parent_and_leaf(tmp_path):
    documents, canon, _, session, _, _, _ = source()
    real = tmp_path / "real"
    real.mkdir()
    path = real / EXPORT_FILENAME
    path.write_text(json.dumps(exported(documents, canon, session)), encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        load_choice_export(alias / EXPORT_FILENAME)
    link = tmp_path / EXPORT_FILENAME
    link.symlink_to(path)
    with pytest.raises(OSError):
        load_choice_export(link)


def test_fifo_import_fails_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO unavailable")
    path = tmp_path / EXPORT_FILENAME
    os.mkfifo(path)
    with pytest.raises(StudioQuestError):
        load_choice_export(path)


def test_publish_and_restore_rebuilds_choice_page_from_canon(tmp_path):
    documents, canon, visual, session, schedule, assignments, _ = source()
    kwargs = dict(
        authorized=True, expected_source_digest=canon,
        expected_visual_digest=visual, expected_session_digest=session)
    manifest, bundle = compile_director_handoff(
        documents, [], schedule, assignments, **kwargs)
    publication = publish_director_handoff(
        manifest, bundle, tmp_path, authorized=True, documents=documents,
        actions=[], schedule=schedule, assignments=assignments)
    assert publication["file_write_performed"] is True
    assert verify_director_handoff(
        documents, [], schedule, assignments, tmp_path, **kwargs) == manifest
    with pytest.raises(FileExistsError):
        publish_director_handoff(
            manifest, bundle, tmp_path, authorized=True, documents=documents,
            actions=[], schedule=schedule, assignments=assignments)
