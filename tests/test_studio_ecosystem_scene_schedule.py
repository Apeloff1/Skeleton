"""Original NPC scene scheduling: source, session, timing, custody and CLI."""
import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    SCHEMA, compile_scene_schedule, publish_scene_schedule, verify_scene_schedule,
)
from skeleton.ai.agents.jeeves.studio_scene_schedule_tool import (
    REQUEST_SCHEMA, execute_scene_schedule_tool,
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
    schedule = {
        "scene_ticks": {card["scene_id"]: 4 for card in cards},
        "npc_turnaround_ticks": 2, "min_start_ticks": {},
    }
    return docs, source, session, schedule


def test_source_bound_deterministic_schedule_and_causal_order():
    docs, source, session, schedule = fixture()
    before = json.dumps(docs, sort_keys=True)
    receipt = compile_scene_schedule(
        docs, [], schedule, authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert receipt["schema"] == SCHEMA
    assert receipt["session_digest"] == session.digest
    assert receipt["replay_verified"] is True
    assert receipt["file_write_performed"] is False
    assert receipt["release_certified"] is False
    assert receipt["critical_path_ticks"] >= 4
    assert receipt["scene_count"] == len(schedule["scene_ticks"])
    assert all(row["end_tick"] - row["start_tick"] == 4
               for row in receipt["timeline"])
    for row in receipt["timeline"]:
        assert all(parent["end_tick"] <= row["start_tick"]
                   for parent in row["prerequisite_scenes"])
    assert json.dumps(docs, sort_keys=True) == before
    assert receipt == compile_scene_schedule(
        docs, [], schedule, authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)


@pytest.mark.parametrize("bad", [
    {"scene_ticks": {}, "npc_turnaround_ticks": 0, "min_start_ticks": {}},
    {"scene_ticks": {}, "npc_turnaround_ticks": True, "min_start_ticks": {}},
    {"scene_ticks": {}, "npc_turnaround_ticks": 0, "min_start_ticks": {"forged": 1}},
    {"scene_ticks": {}, "npc_turnaround_ticks": 0, "min_start_ticks": {}, "extra": 1},
])
def test_reject_missing_or_forged_authored_schedule(bad):
    docs, source, _, _ = fixture()
    with pytest.raises(StudioQuestError):
        compile_scene_schedule(docs, [], bad, authorized=True,
                               expected_source_digest=source)


def test_stale_source_session_and_untrusted_actions_fail_closed():
    docs, source, session, schedule = fixture()
    for kwargs in ({"expected_source_digest": "0" * 64},
                   {"expected_source_digest": True},
                   {"expected_source_digest": source, "expected_session_digest": "0" * 64},
                   {"expected_source_digest": source, "expected_session_digest": True}):
        with pytest.raises(StudioQuestError):
            compile_scene_schedule(docs, [], schedule, authorized=True, **kwargs)
    with pytest.raises(StudioQuestError):
        compile_scene_schedule(docs, [["forged", "choice"]], schedule,
                               authorized=True, expected_source_digest=source)
    with pytest.raises(PermissionError):
        compile_scene_schedule(docs, [], schedule, authorized=False,
                               expected_source_digest=source)


def test_private_exclusive_publish_and_verified_restore(tmp_path):
    docs, source, session, schedule = fixture()
    receipt = compile_scene_schedule(
        docs, [], schedule, authorized=True, expected_source_digest=source)
    published = publish_scene_schedule(receipt, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    path = tmp_path / "scene_schedule.json"
    assert path.is_file()
    assert path.stat().st_mode & 0o077 == 0
    assert verify_scene_schedule(
        docs, [], tmp_path, authorized=True, expected_source_digest=source) == receipt
    with pytest.raises(FileExistsError):
        publish_scene_schedule(receipt, tmp_path, authorized=True)
    assert json.loads(path.read_text()) == receipt
    with pytest.raises(StudioQuestError):
        verify_scene_schedule(docs, [], tmp_path, authorized=True,
                              expected_source_digest="0" * 64)
    assert session.digest == receipt["session_digest"]


def test_tampering_and_symlink_destination_fail_closed(tmp_path):
    docs, source, _, schedule = fixture()
    receipt = compile_scene_schedule(
        docs, [], schedule, authorized=True, expected_source_digest=source)
    other = tmp_path / "target"
    other.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(other, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported by this platform")
    with pytest.raises(OSError):
        publish_scene_schedule(receipt, linked, authorized=True)
    published = publish_scene_schedule(receipt, other, authorized=True)
    path = Path(published["path"])
    altered = dict(receipt)
    altered["critical_path_ticks"] += 1
    path.write_text(json.dumps(altered))
    with pytest.raises(StudioQuestError):
        verify_scene_schedule(docs, [], other, authorized=True,
                              expected_source_digest=source)


def test_jeeves_router_and_operator_cli_parity(capsys):
    from scripts.studio_scene_schedule_cli import main
    docs, source, session, schedule = fixture()
    request = {"schema": REQUEST_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source,
               "expected_session_digest": session.digest,
               "actions": [], "schedule": schedule}
    direct = execute_scene_schedule_tool(request, authorized=True)
    routed = route_world_tool({"tool": "studio_authored_scene_schedule",
                               "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert any(x["name"] == "studio_authored_scene_schedule"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--expected-session", session.digest,
                 "--schedule", json.dumps(schedule)]) == 0
    assert json.loads(capsys.readouterr().out) == direct["detail"]
    with pytest.raises(StudioQuestError):
        execute_scene_schedule_tool({**request, "authority": True}, authorized=True)
    with pytest.raises(PermissionError):
        execute_scene_schedule_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--schedule", '{"scene_ticks":{},"scene_ticks":{}}'])
