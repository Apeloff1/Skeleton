"""Source-leased browser export -> strict CLI -> playable compiler."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_director_authoring import (
    FILENAME, SCHEMA, load_director_authoring,
)
from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
    compile_director_handoff,
)
from scripts.studio_director_handoff_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    visual = sha256(json.dumps(
        docs["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    session = replay_quest(docs, [], authorized=True).digest
    scenes = docs["scene"]["episode_plan"]
    schedule = {
        "scene_ticks": {scene["id"]: 5 for scene in scenes},
        "npc_turnaround_ticks": 2, "min_start_ticks": {},
    }
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    assignments = {
        scene["id"]: {
            asset: recipe for asset in scene["assets"] + scene["interactive_objects"]
        } for scene in scenes
    }
    export = {
        "schema": SCHEMA, "source_digest": source,
        "visual_digest": visual, "session_digest": session,
        "schedule": schedule, "assignments": assignments,
    }
    return docs, export


def write_export(directory, value):
    path = directory / FILENAME
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def import_export(path, export, **kwargs):
    return load_director_authoring(
        path, authorized=True, expected_source_digest=export["source_digest"],
        expected_visual_digest=export["visual_digest"],
        expected_session_digest=export["session_digest"], **kwargs)


def test_export_roundtrip_recompiles_playable_and_cli(tmp_path, capsys):
    docs, export = fixture()
    path = write_export(tmp_path, export)
    schedule, assignments = import_export(path, export)
    assert (schedule, assignments) == (export["schedule"], export["assignments"])
    kwargs = dict(
        authorized=True, expected_source_digest=export["source_digest"],
        expected_visual_digest=export["visual_digest"],
        expected_session_digest=export["session_digest"],
    )
    manifest, bundle = compile_director_handoff(
        docs, [], schedule, assignments, **kwargs)
    assert manifest["canonical_html5_gameplay_replay_verified"] is True
    assert manifest["release_certified"] is False
    assert bundle.startswith(b"PK")
    assert main([
        "--project", PROJECT, "--expected-source", export["source_digest"],
        "--expected-visual", export["visual_digest"],
        "--expected-session", export["session_digest"],
        "--editor-export", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == manifest


def test_export_is_only_a_request_not_a_proof(tmp_path):
    docs, export = fixture()
    path = write_export(tmp_path, export)
    with pytest.raises(PermissionError):
        load_director_authoring(
            path, authorized=False, expected_source_digest=export["source_digest"],
            expected_visual_digest=export["visual_digest"])
    with pytest.raises(StudioQuestError, match="stale"):
        load_director_authoring(
            path, authorized=True, expected_source_digest="0" * 64,
            expected_visual_digest=export["visual_digest"])
    forged = dict(export)
    forged["assignments"] = {"unrecognized_scene": {}}
    path = write_export(tmp_path, forged)
    schedule, assignments = import_export(path, export)
    with pytest.raises(StudioQuestError):
        compile_director_handoff(
            docs, [], schedule, assignments, authorized=True,
            expected_source_digest=export["source_digest"],
            expected_visual_digest=export["visual_digest"],
            expected_session_digest=export["session_digest"])


@pytest.mark.parametrize("mutation", [
    lambda data: data.replace(b'"schema":', b'"schema":"forged","schema":', 1),
    lambda data: data.replace(b'"schema":', b'"extra":true,"schema":', 1),
    lambda data: b'{"schema":NaN}',
    lambda data: b'{"schema":',
    lambda data: b'X' * (64 * 1024 + 1),
])
def test_malformed_duplicate_extra_nonfinite_and_oversized_fail(tmp_path, mutation):
    _, export = fixture()
    path = write_export(tmp_path, export)
    path.write_bytes(mutation(path.read_bytes()))
    with pytest.raises(StudioQuestError):
        import_export(path, export)


def test_symlink_and_fifo_fail_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO unavailable")
    _, export = fixture()
    path = write_export(tmp_path, export)
    original = tmp_path / "source.json"
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(OSError):
        import_export(path, export)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(StudioQuestError):
        import_export(path, export)


def test_cli_rejects_conflicting_inline_and_export(tmp_path):
    _, export = fixture()
    path = write_export(tmp_path, export)
    with pytest.raises(SystemExit):
        main([
            "--project", PROJECT, "--expected-source", export["source_digest"],
            "--expected-visual", export["visual_digest"],
            "--editor-export", str(path), "--schedule", "{}",
        ])


def test_editor_export_session_is_enforced_even_without_cli_session(tmp_path):
    _, export = fixture()
    stale = dict(export)
    stale["session_digest"] = "0" * 64
    path = write_export(tmp_path, stale)
    with pytest.raises(SystemExit):
        main([
            "--project", PROJECT, "--expected-source", export["source_digest"],
            "--expected-visual", export["visual_digest"],
            "--editor-export", str(path),
        ])


def test_cli_publishes_and_restores_imported_export(tmp_path, capsys):
    _, export = fixture()
    incoming = tmp_path / "incoming"
    outgoing = tmp_path / "private"
    incoming.mkdir()
    outgoing.mkdir()
    path = write_export(incoming, export)
    args = [
        "--project", PROJECT, "--expected-source", export["source_digest"],
        "--expected-visual", export["visual_digest"],
        "--editor-export", str(path),
    ]
    assert main(args + ["--publish-directory", str(outgoing)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["publication"]["file_write_performed"] is True
    assert result["manifest"]["release_certified"] is False
    assert (outgoing / "studio_director_handoff.zip").is_file()
    assert main(args + ["--verify-directory", str(outgoing)]) == 0
    assert json.loads(capsys.readouterr().out) == result["manifest"]
    with pytest.raises(SystemExit):
        main(args + ["--publish-directory", str(outgoing)])


def test_symlinked_parent_directory_rejected(tmp_path):
    _, export = fixture()
    real = tmp_path / "real"
    real.mkdir()
    write_export(real, export)
    link = tmp_path / "alias"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        import_export(link / FILENAME, export)
