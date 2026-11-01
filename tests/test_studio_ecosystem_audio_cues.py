"""Source-to-playable audio cue handoff: deterministic fixtures and fail-closed edits."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_audio_cues import (
    REQUEST_SCHEMA, FILENAME, compile_audio_cues,
    publish_audio_cues, verify_published_audio_cues,
)
from skeleton.ai.agents.jeeves.studio_audio_cue_tool import (
    REQUEST_SCHEMA as JEEVES_SCHEMA, execute_audio_cue_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    documents = read_blueprint(PROJECT)
    source = audit_canon_source(documents, authorized=True)["source_digest"]
    session = replay_quest(documents, [], authorized=True).digest
    scenes = documents["scene"]["episode_plan"]
    schedule = {
        "scene_ticks": {scene["id"]: 12 for scene in scenes},
        "npc_turnaround_ticks": 2, "min_start_ticks": {},
    }
    layers = documents["audio"]["sound_layers"]
    authored = {
        "schema": REQUEST_SCHEMA,
        "scene_cues": {
            scene["id"]: [
                {"layer_id": layers[0]["id"], "start_offset": 0,
                 "duration_ticks": 4,
                 "caption": "Wind across the original fjord."},
                {"layer_id": layers[1]["id"], "start_offset": 5,
                 "duration_ticks": 3,
                 "caption": "A measured action cue."},
            ] for scene in scenes
        },
    }
    return documents, source, session, schedule, authored


def compile_fixture():
    docs, source, session, schedule, authored = fixture()
    plan = compile_audio_cues(
        docs, [], schedule, authored, authorized=True,
        expected_source_digest=source, expected_session_digest=session)
    return docs, source, session, schedule, authored, plan


def test_source_leased_audio_cues_compile_deterministically():
    docs, source, session, schedule, authored, plan = compile_fixture()
    assert plan["schema"] == "skeleton.game_builder.studio_audio_cue_plan.v1"
    assert plan["source_digest"] == source
    assert plan["session_digest"] == session
    assert plan["scene_count"] == len(docs["scene"]["episode_plan"])
    assert plan["cue_count"] == 2 * plan["scene_count"]
    assert plan["source_replay_verified"] is True
    assert plan["captions_authored"] is True
    assert plan["audio_recorded_verified"] is False
    assert plan["native_audio_verified"] is False
    assert plan["release_certified"] is False
    assert plan == compile_audio_cues(
        docs, [], schedule, authored, authorized=True,
        expected_source_digest=source, expected_session_digest=session)
    for scene in plan["scenes"]:
        assert scene["start_tick"] <= scene["cues"][0]["start_tick"]
        assert scene["cues"][-1]["end_tick"] <= scene["end_tick"]
        assert scene["scene_audio_digest"]
        assert all(cue["caption_runtime_verified"] is False
                   for cue in scene["cues"])


@pytest.mark.parametrize("change", [
    lambda r: r.update(schema="wrong"),
    lambda r: r.update(unexpected=True),
    lambda r: r["scene_cues"].pop("origin"),
    lambda r: r["scene_cues"]["origin"][0].update(layer_id="not_an_authored_layer"),
    lambda r: r["scene_cues"]["origin"][0].update(start_offset=True),
    lambda r: r["scene_cues"]["origin"][0].update(duration_ticks=0),
    lambda r: r["scene_cues"]["origin"][0].update(duration_ticks=999),
    lambda r: r["scene_cues"]["origin"][0].update(caption="<script>\nattack</script>"),
    lambda r: r["scene_cues"]["origin"][0].update(caption=""),
    lambda r: r["scene_cues"]["origin"][0].update(extra="forged"),
    lambda r: r["scene_cues"]["origin"][1].update(
        layer_id=r["scene_cues"]["origin"][0]["layer_id"], start_offset=2),
    lambda r: r["scene_cues"]["origin"].clear(),
])
def test_malformed_authoring_fails_closed(change):
    docs, source, session, schedule, authored = fixture()
    change(authored)
    with pytest.raises(StudioQuestError):
        compile_audio_cues(
            docs, [], schedule, authored, authorized=True,
            expected_source_digest=source, expected_session_digest=session)


def test_source_session_and_accessibility_custody():
    docs, source, session, schedule, authored = fixture()
    for stale_source, stale_session in [
        ("0" * 64, session), (source, "0" * 64),
        ("not-a-digest", session),
    ]:
        with pytest.raises(StudioQuestError):
            compile_audio_cues(
                docs, [], schedule, authored, authorized=True,
                expected_source_digest=stale_source,
                expected_session_digest=stale_session)
    with pytest.raises(PermissionError):
        compile_audio_cues(
            docs, [], schedule, authored, authorized=False,
            expected_source_digest=source)
    modified = deepcopy(docs)
    modified["audio"]["audio_accessibility"] = ["adjustable_mixer"]
    with pytest.raises(StudioQuestError):
        compile_audio_cues(
            modified, [], schedule, authored, authorized=True,
            expected_source_digest=source)
    modified = deepcopy(docs)
    modified["audio"]["sound_layers"][1]["id"] = modified["audio"]["sound_layers"][0]["id"]
    with pytest.raises(StudioQuestError):
        compile_audio_cues(
            modified, [], schedule, authored, authorized=True,
            expected_source_digest=source)


def test_private_published_cue_plan_replays_and_detects_tampering(tmp_path):
    docs, source, session, schedule, authored, plan = compile_fixture()
    kwargs = {
        "documents": docs, "actions": [], "schedule": schedule,
        "request": authored,
    }
    publication = publish_audio_cues(
        plan, tmp_path, authorized=True, **kwargs)
    assert publication["file_write_performed"] is True
    assert publication["sha256"] == sha256((tmp_path / FILENAME).read_bytes()).hexdigest()
    assert (tmp_path / FILENAME).stat().st_mode & 0o077 == 0
    assert verify_published_audio_cues(
        tmp_path, authorized=True, expected_source_digest=source,
        expected_session_digest=session, **kwargs) == plan
    with pytest.raises(FileExistsError):
        publish_audio_cues(plan, tmp_path, authorized=True, **kwargs)
    (tmp_path / FILENAME).write_text('{"schema":"forged"}', encoding="utf-8")
    with pytest.raises(StudioQuestError):
        verify_published_audio_cues(
            tmp_path, authorized=True, expected_source_digest=source,
            expected_session_digest=session, **kwargs)


def test_publisher_rejects_rehashed_forged_native_claim(tmp_path):
    docs, _, _, schedule, authored, plan = compile_fixture()
    forged = dict(plan)
    forged["audio_recorded_verified"] = True
    with pytest.raises(StudioQuestError):
        publish_audio_cues(
            forged, tmp_path, authorized=True, documents=docs,
            actions=[], schedule=schedule, request=authored)
    assert not (tmp_path / FILENAME).exists()


def test_jeeves_tool_router_is_read_only_and_authorized():
    docs, source, session, schedule, authored = fixture()
    request = {
        "schema": JEEVES_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "expected_session_digest": session,
        "actions": [], "schedule": schedule, "authoring": authored,
    }
    direct = execute_audio_cue_tool(request, authorized=True)
    assert direct["detail"]["source_digest"] == source
    assert direct["file_write_performed"] is False
    routed = route_world_tool(
        {"tool": "studio_original_audio_caption_cues", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert any(entry["name"] == "studio_original_audio_caption_cues"
               for entry in world_tool_catalog()["tools"])
    with pytest.raises(PermissionError):
        execute_audio_cue_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_audio_cue_tool({**request, "authorized": True}, authorized=True)


def test_cli_matches_canonical_compiler(capsys):
    from scripts.studio_audio_cues_cli import main
    _, source, session, schedule, authored, plan = compile_fixture()
    args = [
        "--project", PROJECT, "--expected-source", source,
        "--expected-session", session,
        "--schedule", json.dumps(schedule),
        "--authoring-json", json.dumps(authored),
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == plan


def test_cli_persist_and_verify_replay(capsys, tmp_path):
    from scripts.studio_audio_cues_cli import main
    _, source, session, schedule, authored, plan = compile_fixture()
    args = [
        "--project", PROJECT, "--expected-source", source,
        "--expected-session", session,
        "--schedule", json.dumps(schedule),
        "--authoring-json", json.dumps(authored),
    ]
    assert main(args + ["--publish-directory", str(tmp_path)]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["plan"] == plan
    assert main(args + ["--verify-directory", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == plan
