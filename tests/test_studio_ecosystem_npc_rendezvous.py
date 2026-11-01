"""NPC rendezvous canonical replay, travel, CLI, Jeeves and custody contracts."""
from __future__ import annotations

import json
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    PROMPT as TEMPORAL_PROMPT, propose_temporal_windows,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_transit import compile_npc_transit
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import compile_scene_schedule
from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous import (
    PROMPT, compile_npc_rendezvous, propose_npc_rendezvous,
    replay_npc_rendezvous, compile_rendezvous_playable,
    publish_npc_rendezvous, restore_npc_rendezvous,
)
from skeleton.ai.agents.jeeves.studio_npc_rendezvous_tool import (
    REQUEST_SCHEMA, execute_npc_rendezvous_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    temporal = propose_temporal_windows(
        docs, [], TEMPORAL_PROMPT, authorized=True,
        expected_source_digest=source)["detail"]
    schedule = compile_scene_schedule(
        docs, [], temporal["authoring"]["schedule_request"], authorized=True,
        expected_source_digest=source)
    sites = sorted({row["site"] for row in schedule["timeline"]})
    graph = {"edges": [
        {"from_site": a, "to_site": b, "ticks": 0}
        for a in sites for b in sites if a != b
    ]}
    transit = compile_npc_transit(docs, temporal, graph, authorized=True)
    return docs, source, transit, schedule


def meeting(schedule, *, start=0, latest=10000, site=None, cast=None):
    rows = schedule["timeline"]
    names = sorted({row["npc_id"] for row in rows})
    if len(names) < 2:
        pytest.skip("source has fewer than two NPCs")
    return {
        "id": "first-meeting", "npc_ids": cast or names[:2],
        "site": site or sorted({row["site"] for row in rows})[0],
        "earliest_tick": start, "latest_tick": latest,
        "duration_ticks": 1,
    }


def test_prompt_is_deterministic_source_bound_and_replayed():
    docs, source, transit, _ = fixture()
    result = propose_npc_rendezvous(
        docs, transit, PROMPT, authorized=True, expected_source_digest=source)
    assert result == propose_npc_rendezvous(
        docs, transit, PROMPT, authorized=True, expected_source_digest=source)
    assert replay_npc_rendezvous(docs, result, authorized=True) == result
    assert result["model_inference_performed"] is False
    assert result["physical_travel_verified"] is False
    assert result["release_certified"] is False


def test_meeting_occupancy_and_ordered_reservations():
    docs, source, transit, schedule = fixture()
    first = meeting(schedule)
    second = {**first, "id": "second-meeting"}
    result = compile_npc_rendezvous(
        docs, transit, [first, second], authorized=True,
        expected_source_digest=source)
    assert len(result["outcomes"]) == 2
    if result["outcomes"][0]["status"] == "accepted":
        assert result["outcomes"][1]["start_tick"] is None or (
            result["outcomes"][1]["start_tick"] >=
            result["outcomes"][0]["end_tick"])
    assert replay_npc_rendezvous(docs, result, authorized=True) == result


def test_unreachable_and_stale_source_fail_closed():
    docs, source, transit, schedule = fixture()
    authored = meeting(schedule)
    missing = compile_npc_transit(
        docs, transit["temporal_receipt"], {"edges": []}, authorized=True)
    result = compile_npc_rendezvous(
        docs, missing, [authored], authorized=True,
        expected_source_digest=source)
    assert result["release_certified"] is False
    if not result["playable_handoff_allowed"]:
        with pytest.raises(StudioQuestError):
            compile_rendezvous_playable(docs, result, authorized=True)
    with pytest.raises(StudioQuestError):
        compile_npc_rendezvous(
            docs, transit, [authored], authorized=True,
            expected_source_digest="0" * 64)
    with pytest.raises(PermissionError):
        compile_npc_rendezvous(
            docs, transit, [authored], authorized=False,
            expected_source_digest=source)


def test_malformed_meetings_and_forged_receipts():
    docs, source, transit, schedule = fixture()
    valid = meeting(schedule)
    for bad in (
        [{**valid, "npc_ids": [valid["npc_ids"][0]] * 2}],
        [{**valid, "duration_ticks": True}],
        [{**valid, "site": "invented-site"}],
        [{**valid, "latest_tick": 0}],
        [valid, valid],
        [valid] * 17,
        [{**valid, "authorized": True}],
    ):
        with pytest.raises(StudioQuestError):
            compile_npc_rendezvous(
                docs, transit, bad, authorized=True,
                expected_source_digest=source)
    result = compile_npc_rendezvous(
        docs, transit, [valid], authorized=True,
        expected_source_digest=source)
    for forged in ({**result, "accepted_count": 999},
                   {**result, "release_certified": True},
                   {**result, "source_digest": "0" * 64}):
        with pytest.raises(StudioQuestError):
            replay_npc_rendezvous(docs, forged, authorized=True)


def test_private_custody_replay_nooverwrite_symlink(tmp_path):
    docs, source, transit, schedule = fixture()
    result = compile_npc_rendezvous(
        docs, transit, [meeting(schedule)], authorized=True,
        expected_source_digest=source)
    saved = publish_npc_rendezvous(docs, result, tmp_path, authorized=True)
    assert saved["file_write_performed"]
    target = tmp_path / "npc_rendezvous.json"
    assert target.stat().st_mode & 0o077 == 0
    assert restore_npc_rendezvous(
        docs, tmp_path, authorized=True, expected_source_digest=source) == result
    with pytest.raises(FileExistsError):
        publish_npc_rendezvous(docs, result, tmp_path, authorized=True)
    target.write_text('{"schema":"x","schema":"y"}')
    with pytest.raises(StudioQuestError):
        restore_npc_rendezvous(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_npc_rendezvous(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_jeeves_router_and_cli(capsys):
    from scripts.studio_npc_rendezvous_cli import main
    docs, source, transit, _ = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "transit_receipt": transit,
        "prompt": PROMPT,
    }
    direct = execute_npc_rendezvous_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_rendezvous", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(item["name"] == "studio_original_npc_rendezvous"
               for item in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--transit", json.dumps(transit), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["rendezvous"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_rendezvous_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_npc_rendezvous_tool(
            {**request, "authorized": True}, authorized=True)


def test_offline_editor_export_import_and_recompile(tmp_path, capsys):
    from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous_editor import (
        EXPORT_SCHEMA, render_npc_rendezvous_editor,
        load_npc_rendezvous_editor_export, publish_npc_rendezvous_editor,
    )
    from scripts.studio_npc_rendezvous_cli import main
    docs, source, transit, schedule = fixture()
    result = compile_npc_rendezvous(
        docs, transit, [meeting(schedule)], authorized=True,
        expected_source_digest=source)
    html, proof = render_npc_rendezvous_editor(docs, result, authorized=True)
    from hashlib import sha256
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert b"Export typed NPC rendezvous edits" in html
    published = publish_npc_rendezvous_editor(
        docs, result, tmp_path, authorized=True)
    assert published["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_npc_rendezvous_editor(docs, result, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": result["project_id"],
        "source_digest": source, "session_digest": result["session_digest"],
        "transit_digest": result["transit_digest"],
        "baseline_rendezvous_digest": result["rendezvous_digest"],
        "meetings": result["meetings"],
    }
    path = tmp_path / "npc_rendezvous_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": result["project_id"],
        "expected_source_digest": source,
        "expected_session_digest": result["session_digest"],
        "expected_transit_digest": result["transit_digest"],
        "expected_baseline_digest": result["rendezvous_digest"],
    }
    assert load_npc_rendezvous_editor_export(path, **kwargs) == result["meetings"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--transit", json.dumps(transit),
        "--baseline-rendezvous", json.dumps(result),
        "--import-meetings", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["rendezvous"] == result
    path.write_text(json.dumps({**record, "source_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_npc_rendezvous_editor_export(path, **kwargs)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_npc_rendezvous_editor_export(path, **kwargs)
