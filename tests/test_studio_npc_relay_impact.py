"""NPC relay impact source, counterfactual and private custody contracts."""
from __future__ import annotations

import copy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    PROMPT as TEMPORAL_PROMPT, propose_temporal_windows,
)
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import compile_scene_schedule
from skeleton.ai.game_builder.studio_ecosystem_npc_transit import compile_npc_transit
from skeleton.ai.game_builder.studio_ecosystem_npc_rendezvous import compile_npc_rendezvous
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge import (
    REQUEST_SCHEMA as KNOWLEDGE_SCHEMA, source_knowledge_facts, compile_npc_knowledge,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange import (
    PROMPT as EXCHANGE_PROMPT, propose_npc_knowledge_exchange,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_relay import (
    compile_npc_knowledge_relay, propose_npc_knowledge_relay, PROMPT as RELAY_PROMPT,
)
from skeleton.ai.game_builder.studio_npc_relay_impact import (
    PROMPT, SCHEMA, compile_npc_relay_impact, propose_npc_relay_impact,
    replay_npc_relay_impact, compile_npc_relay_impact_playable,
    publish_npc_relay_impact, restore_npc_relay_impact, FILENAME,
)
from skeleton.ai.game_builder.studio_npc_relay_impact_view import (
    render_npc_relay_impact_review, publish_npc_relay_impact_review,
    FILENAME as REVIEW_FILENAME,
)
from skeleton.ai.agents.jeeves.studio_npc_relay_impact_tool import (
    REQUEST_SCHEMA, execute_npc_relay_impact_tool,
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
        docs, [], temporal["authoring"]["schedule_request"],
        authorized=True, expected_source_digest=source)
    sites = sorted({row["site"] for row in schedule["timeline"]})
    graph = {"edges": [
        {"from_site": a, "to_site": b, "ticks": 0}
        for a in sites for b in sites if a != b
    ]}
    transit = compile_npc_transit(docs, temporal, graph, authorized=True)
    cast = sorted({row["npc_id"] for row in schedule["timeline"]})
    if len(cast) < 2:
        pytest.skip("source has fewer than two NPCs")
    rendezvous = compile_npc_rendezvous(
        docs, transit, [{
            "id": "impact_meeting", "npc_ids": cast[:2], "site": sites[0],
            "earliest_tick": 0, "latest_tick": min(
                1000000, max(row["end_tick"] for row in schedule["timeline"]) + 100),
            "duration_ticks": 1,
        }], authorized=True, expected_source_digest=source)
    facts = source_knowledge_facts(
        docs, [], authorized=True, expected_source_digest=source)
    candidates = [
        {"fact_id": fact["fact_id"], "recipient_scene_id": dest["scene_id"],
         "required_alternative": None}
        for fact in facts["facts"]
        for dest in schedule["timeline"]
        if dest["npc_id"] != fact["npc_id"]
        and dest["scene_index"] > next(
            row["scene_index"] for row in schedule["timeline"]
            if row["scene_id"] == fact["scene_id"])
    ]
    knowledge = compile_npc_knowledge(
        docs, [], {"schema": KNOWLEDGE_SCHEMA, "reveals": candidates[:1]},
        authorized=True, expected_source_digest=source)
    exchange = propose_npc_knowledge_exchange(
        docs, rendezvous, knowledge, EXCHANGE_PROMPT,
        authorized=True, expected_source_digest=source)
    baseline = compile_npc_knowledge_relay(
        docs, exchange, {"routes": []}, authorized=True,
        expected_source_digest=source)
    candidate = propose_npc_knowledge_relay(
        docs, exchange, RELAY_PROMPT, authorized=True,
        expected_source_digest=source)
    return docs, source, baseline, candidate


def test_source_bound_impact_deterministic_replay_and_no_speech_claim():
    docs, source, baseline, candidate = fixture()
    result = propose_npc_relay_impact(
        docs, baseline, candidate, PROMPT, authorized=True,
        expected_source_digest=source)
    assert result["schema"] == SCHEMA
    assert result == compile_npc_relay_impact(
        docs, baseline, candidate, authorized=True,
        expected_source_digest=source)
    assert replay_npc_relay_impact(docs, result, authorized=True) == result
    assert result["npc_speech_verified"] is False
    assert result["native_npc_memory_verified"] is False
    assert result["release_certified"] is False
    assert all(row["source_text_in_impact_row"] is False for row in result["changes"])
    assert result["changed_route_count"] == len(result["changes"])
    if candidate["routes"]:
        assert result["changed_route_count"] == len(candidate["routes"])
        assert set(result["affected_scene_ids"]) == {
            row["target_scene_id"] for row in candidate["routes"]
        }
    with pytest.raises(StudioQuestError):
        compile_npc_relay_impact_playable(docs, result, authorized=True)


def test_forgery_stale_source_authority_and_bool_int_substitution():
    docs, source, baseline, candidate = fixture()
    valid = compile_npc_relay_impact(
        docs, baseline, candidate, authorized=True,
        expected_source_digest=source)
    with pytest.raises(PermissionError):
        compile_npc_relay_impact(
            docs, baseline, candidate, authorized=False,
            expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        compile_npc_relay_impact(
            docs, baseline, candidate, authorized=True,
            expected_source_digest="0" * 64)
    for name, value in (
        ("changed_route_count", 999),
        ("source_replay_verified", 1),
        ("release_certified", True),
        ("delivery_regressions", False),
        ("affected_scene_ids", ["forged_scene"]),
    ):
        forged = copy.deepcopy(valid)
        forged[name] = value
        with pytest.raises(StudioQuestError):
            replay_npc_relay_impact(docs, forged, authorized=True)
    stale = copy.deepcopy(candidate)
    stale["source_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_npc_relay_impact(
            docs, baseline, stale, authorized=True,
            expected_source_digest=source)


def test_private_publish_restore_no_overwrite_or_symlink(tmp_path):
    docs, source, baseline, candidate = fixture()
    valid = compile_npc_relay_impact(
        docs, baseline, candidate, authorized=True,
        expected_source_digest=source)
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    evidence = publish_npc_relay_impact(
        docs, valid, directory, authorized=True)
    assert evidence["file_write_performed"] is True
    assert restore_npc_relay_impact(
        docs, directory, authorized=True,
        expected_source_digest=source) == valid
    with pytest.raises(FileExistsError):
        publish_npc_relay_impact(docs, valid, directory, authorized=True)
    (directory / FILENAME).unlink()
    (directory / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((OSError, StudioQuestError)):
        restore_npc_relay_impact(
            docs, directory, authorized=True, expected_source_digest=source)


def test_jeeves_typed_router_and_fail_closed_handoff():
    docs, source, baseline, candidate = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "baseline_receipt": baseline, "candidate_receipt": candidate,
    }
    from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _canonical
    if len(_canonical(request)) <= 60 * 1024:
        direct = execute_npc_relay_impact_tool(request, authorized=True)
        assert direct["detail"]["source_replay_verified"] is True
        assert direct["release_certified"] is False
    else:
        with pytest.raises(StudioQuestError):
            execute_npc_relay_impact_tool(request, authorized=True)
    names = {entry["name"] for entry in world_tool_catalog()["tools"]}
    assert "studio_original_npc_relay_impact" in names
    envelope = {"tool": "studio_original_npc_relay_impact",
                "arguments": request}
    if len(_canonical(request)) <= 60 * 1024 and len(_canonical(envelope)) <= 64 * 1024:
        routed = route_world_tool(envelope, authorized=True)
        assert routed["result"]["detail"] == direct["detail"]
    else:
        with pytest.raises(StudioQuestError):
            route_world_tool(envelope, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(envelope, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_npc_relay_impact_tool(
            {**request, "authorized": True}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_npc_relay_impact_tool(
            {**request, "playable_manifest": 1}, authorized=True)

def test_identical_receipts_have_no_affected_scenes_or_regressions():
    docs, source, baseline, _ = fixture()
    result = compile_npc_relay_impact(
        docs, baseline, baseline, authorized=True,
        expected_source_digest=source)
    assert result["changes"] == []
    assert result["affected_scene_ids"] == []
    assert result["changed_route_count"] == 0
    assert result["delivery_regressions"] == 0
    assert result["playable_handoff_allowed"] is False


def test_private_offline_html_review_excludes_source_prose_and_scripts(tmp_path):
    docs, source, baseline, candidate = fixture()
    impact = compile_npc_relay_impact(
        docs, baseline, candidate, authorized=True,
        expected_source_digest=source)
    raw = render_npc_relay_impact_review(docs, impact, authorized=True)
    assert b"Content-Security-Policy" in raw
    assert b"default-src 'none'" in raw
    assert b"<script" not in raw
    assert b"NOT VERIFIED" in raw
    assert impact["impact_digest"].encode("ascii") in raw
    directory = tmp_path / "review"
    directory.mkdir(mode=0o700)
    result = publish_npc_relay_impact_review(
        docs, impact, directory, authorized=True)
    assert result["file_write_performed"] is True
    assert (directory / REVIEW_FILENAME).read_bytes() == raw
    with pytest.raises(FileExistsError):
        publish_npc_relay_impact_review(
            docs, impact, directory, authorized=True)
    with pytest.raises(PermissionError):
        render_npc_relay_impact_review(
            docs, impact, authorized=False)
