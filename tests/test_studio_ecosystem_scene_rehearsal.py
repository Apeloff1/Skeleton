"""Regression fixtures for source-leased scene what-if and playable custody."""
from __future__ import annotations
from hashlib import sha256
import io
import json
import zipfile
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_scene_rehearsal import (
    compile_scene_rehearsal, compile_rehearsed_playable,
    publish_scene_rehearsal, verify_scene_rehearsal,
)
from skeleton.ai.agents.jeeves.studio_scene_rehearsal_tool import (
    REQUEST_SCHEMA, execute_scene_rehearsal_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    cards = compile_dialogue_staging(
        docs, [], authorized=True, expected_source_digest=source)["cards"]
    old = {"scene_ticks": {card["scene_id"]: 8 for card in cards},
           "npc_turnaround_ticks": 3, "min_start_ticks": {}}
    new = {"scene_ticks": {card["scene_id"]: 4 for card in cards},
           "npc_turnaround_ticks": 1, "min_start_ticks": {}}
    return docs, source, session, old, new


def test_deterministic_critical_path_and_no_source_mutation():
    docs, source, session, old, new = fixture()
    snapshot = json.dumps(docs, sort_keys=True)
    result = compile_scene_rehearsal(
        docs, [], old, new, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    assert result["candidate_is_shorter"] is True
    assert result["critical_delta_ticks"] < 0
    assert result["changed_scene_count"] > 0
    assert result["candidate_critical_chain"]
    assert result["source_replay_verified"] is True
    assert result["native_timing_verified"] is False
    assert result["file_write_performed"] is False
    assert json.dumps(docs, sort_keys=True) == snapshot
    assert result == compile_scene_rehearsal(
        docs, [], old, new, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    for proof in result["candidate_dependency_proof"]:
        assert proof["end_tick"] > proof["start_tick"]
        assert all(edge["kind"] in ("quest", "npc_turnaround")
                   for edge in proof["binding_edges"])


def test_equal_schedule_and_fail_closed_inputs():
    docs, source, session, old, new = fixture()
    equal = compile_scene_rehearsal(
        docs, [], old, old, authorized=True, expected_source_digest=source)
    assert equal["critical_delta_ticks"] == 0
    assert equal["changed_scene_count"] == 0
    with pytest.raises(PermissionError):
        compile_scene_rehearsal(docs, [], old, new, authorized=False,
                                expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        compile_scene_rehearsal(docs, [], old, new, authorized=True,
                                expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        compile_scene_rehearsal(docs, [], old, new, authorized=True,
                                expected_source_digest=source,
                                expected_session_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        compile_scene_rehearsal(docs, [["forged", "choice"]], old, new,
                                authorized=True, expected_source_digest=source)
    bad = {**new, "scene_ticks": {**new["scene_ticks"],
           next(iter(new["scene_ticks"])): True}}
    with pytest.raises(StudioQuestError):
        compile_scene_rehearsal(docs, [], old, bad, authorized=True,
                                expected_source_digest=source)


def test_private_restore_rejects_forgery_and_symlink(tmp_path):
    docs, source, session, old, new = fixture()
    result = compile_scene_rehearsal(
        docs, [], old, new, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    published = publish_scene_rehearsal(
        result, tmp_path, authorized=True, documents=docs, actions=[])
    assert published["file_write_performed"] is True
    target = tmp_path / "scene_rehearsal.json"
    assert target.stat().st_mode & 0o077 == 0
    assert verify_scene_rehearsal(
        docs, [], tmp_path, authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest) == result
    with pytest.raises(FileExistsError):
        publish_scene_rehearsal(result, tmp_path, authorized=True,
                                documents=docs, actions=[])
    forged = {**result, "candidate_critical_ticks": 0}
    target.write_text(json.dumps(forged))
    with pytest.raises(StudioQuestError):
        verify_scene_rehearsal(docs, [], tmp_path, authorized=True,
                               expected_source_digest=source)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        verify_scene_rehearsal(docs, [], tmp_path, authorized=True,
                               expected_source_digest=source)


def test_typed_jeeves_cli_parity_and_rejection(capsys):
    from scripts.studio_scene_rehearsal_cli import main
    docs, source, session, old, new = fixture()
    request = {"schema": REQUEST_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source,
               "expected_session_digest": session.digest,
               "actions": [], "baseline_schedule": old,
               "candidate_schedule": new}
    direct = execute_scene_rehearsal_tool(request, authorized=True)
    routed = route_world_tool({"tool": "studio_original_scene_rehearsal",
                               "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert any(x["name"] == "studio_original_scene_rehearsal"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--baseline", json.dumps(old),
                 "--candidate", json.dumps(new)]) == 0
    assert json.loads(capsys.readouterr().out)["rehearsal"] == direct["detail"]
    with pytest.raises(StudioQuestError):
        execute_scene_rehearsal_tool({**request, "authorized": True},
                                     authorized=True)
    with pytest.raises(PermissionError):
        execute_scene_rehearsal_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--baseline", '{"scene_ticks":{},"scene_ticks":{}}',
              "--candidate", json.dumps(new)])


def test_rehearsal_compiles_existing_verified_html5_playable():
    docs, source, session, old, new = fixture()
    report = compile_scene_rehearsal(
        docs, [], old, new, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    assignments = {scene["id"]: {
        asset: recipe for asset in scene["assets"] + scene["interactive_objects"]}
        for scene in docs["scene"]["episode_plan"]}
    visual = sha256(json.dumps(
        docs["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    manifest, bundle = compile_rehearsed_playable(
        docs, [], report, assignments, authorized=True,
        expected_visual_digest=visual)
    assert manifest["scene_schedule_digest"] == report["candidate_schedule_digest"]
    assert manifest["canonical_html5_gameplay_replay_verified"] is True
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert b"<html" in archive.read("index.html")
        for name, digest in manifest["file_hashes"].items():
            assert sha256(archive.read(name)).hexdigest() == digest
    with pytest.raises(StudioQuestError):
        compile_rehearsed_playable(
            docs, [], {**report, "candidate_critical_ticks": 0},
            assignments, authorized=True, expected_visual_digest=visual)
