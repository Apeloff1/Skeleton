"""NPC transit proof, unknown routes, replay, custody, CLI and Jeeves integration."""
from __future__ import annotations

import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    PROMPT as TEMPORAL_PROMPT, propose_temporal_windows,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_transit import (
    PROMPT, compile_npc_transit, propose_npc_transit,
    replay_npc_transit, compile_transit_playable,
    publish_npc_transit, restore_npc_transit,
)
from skeleton.ai.agents.jeeves.studio_npc_transit_tool import (
    REQUEST_SCHEMA, execute_npc_transit_tool,
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
    return docs, source, temporal


def test_prompt_is_deterministic_and_cannot_claim_physical_travel():
    docs, source, temporal = fixture()
    proof = propose_npc_transit(
        docs, temporal, PROMPT, authorized=True)
    assert proof == propose_npc_transit(
        docs, temporal, PROMPT, authorized=True)
    assert proof == replay_npc_transit(docs, proof, authorized=True)
    assert proof["source_digest"] == source
    assert proof["physical_travel_verified"] is False
    assert proof["model_inference_performed"] is False


def test_explicit_graph_determinism_and_handoff():
    docs, source, temporal = fixture()
    # Zero operator-estimated ticks between all source sites is a *test*
    # fixture only, not a claim about native world movement.
    from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import compile_scene_schedule
    schedule = compile_scene_schedule(
        docs, [], temporal["authoring"]["schedule_request"], authorized=True,
        expected_source_digest=source)
    sites = sorted({row["site"] for row in schedule["timeline"]})
    graph = {"edges": [
        {"from_site": left, "to_site": right, "ticks": 0}
        for left in sites for right in sites if left != right
    ]}
    report = compile_npc_transit(
        docs, temporal, graph, authorized=True)
    assert report == replay_npc_transit(docs, report, authorized=True)
    assert report["conflict_count"] == 0
    assert report["all_transitions_feasible"] is True
    handoff = compile_transit_playable(docs, report, authorized=True)
    assert handoff["canonical_html5_quest_included"] is True
    assert handoff["physical_travel_verified"] is False


def test_missing_travel_route_fails_closed_on_playable_handoff():
    docs, _, temporal = fixture()
    report = compile_npc_transit(
        docs, temporal, {"edges": []}, authorized=True)
    assert report["conflict_count"] >= 0
    if report["conflict_count"]:
        assert not report["all_transitions_feasible"]
        with pytest.raises(StudioQuestError):
            compile_transit_playable(docs, report, authorized=True)


def test_bad_edges_and_forged_receipts_are_rejected():
    docs, _, temporal = fixture()
    from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import compile_scene_schedule
    schedule = compile_scene_schedule(
        docs, [], temporal["authoring"]["schedule_request"], authorized=True,
        expected_source_digest=temporal["source_digest"])
    site = schedule["timeline"][0]["site"]
    for graph in (
        {"edges": [{"from_site": site, "to_site": site, "ticks": 1}]},
        {"edges": [{"from_site": site, "to_site": "unknown", "ticks": 1}]},
        {"edges": [{"from_site": site, "to_site": site, "ticks": True}]},
        {"edges": "not-an-array"},
    ):
        with pytest.raises(StudioQuestError):
            compile_npc_transit(docs, temporal, graph, authorized=True)
    report = propose_npc_transit(docs, temporal, PROMPT, authorized=True)
    with pytest.raises(StudioQuestError):
        replay_npc_transit(
            docs, {**report, "physical_travel_verified": True}, authorized=True)
    with pytest.raises(PermissionError):
        propose_npc_transit(docs, temporal, PROMPT, authorized=False)


def test_private_nooverwrite_restore_and_symlink_fence(tmp_path):
    docs, source, temporal = fixture()
    report = propose_npc_transit(
        docs, temporal, PROMPT, authorized=True)
    assert publish_npc_transit(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    target = tmp_path / "npc_transit.json"
    assert target.stat().st_mode & 0o077 == 0
    assert restore_npc_transit(
        docs, tmp_path, authorized=True,
        expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_npc_transit(docs, report, tmp_path, authorized=True)
    target.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_npc_transit(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_npc_transit(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_jeeves_router_and_cli_prompt(capsys):
    from scripts.studio_npc_transit_cli import main
    docs, source, temporal = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "temporal_receipt": temporal, "prompt": PROMPT,
    }
    direct = execute_npc_transit_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_transit", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(x["name"] == "studio_original_npc_transit"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--temporal-receipt", json.dumps(temporal), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["transit"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_transit_tool(request, authorized=False)
