"""Source-bound NPC knowledge transfer across authored meetings."""
from __future__ import annotations

import json
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
    PROMPT, compile_npc_knowledge_exchange, propose_npc_knowledge_exchange,
    replay_npc_knowledge_exchange, compile_knowledge_exchange_playable,
    publish_npc_knowledge_exchange, restore_npc_knowledge_exchange,
)
from skeleton.ai.agents.jeeves.studio_npc_knowledge_exchange_tool import (
    REQUEST_SCHEMA, execute_npc_knowledge_exchange_tool,
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
    meeting = {
        "id": "exchange", "npc_ids": cast[:2], "site": sites[0],
        "earliest_tick": 0,
        "latest_tick": min(1000000, max(row["end_tick"] for row in
                                      schedule["timeline"]) + 100),
        "duration_ticks": 1,
    }
    rendezvous = compile_npc_rendezvous(
        docs, transit, [meeting], authorized=True,
        expected_source_digest=source)
    facts = source_knowledge_facts(
        docs, [], authorized=True, expected_source_digest=source)
    scenes = schedule["timeline"]
    candidates = [
        {"fact_id": fact["fact_id"], "recipient_scene_id": dest["scene_id"],
         "required_alternative": None}
        for fact in facts["facts"]
        for dest in scenes
        if dest["npc_id"] != fact["npc_id"]
        and scenes.index(dest) > next(
            i for i, scene in enumerate(scenes)
            if scene["scene_id"] == fact["scene_id"])
    ]
    knowledge = compile_npc_knowledge(
        docs, [], {"schema": KNOWLEDGE_SCHEMA, "reveals": candidates[:1]},
        authorized=True, expected_source_digest=source)
    return docs, source, rendezvous, knowledge


def test_deterministic_proposal_and_canonical_replay():
    docs, source, rendezvous, knowledge = fixture()
    report = propose_npc_knowledge_exchange(
        docs, rendezvous, knowledge, PROMPT, authorized=True,
        expected_source_digest=source)
    assert report == propose_npc_knowledge_exchange(
        docs, rendezvous, knowledge, PROMPT, authorized=True,
        expected_source_digest=source)
    assert replay_npc_knowledge_exchange(docs, report, authorized=True) == report
    assert report["npc_speech_verified"] is False
    assert report["release_certified"] is False
    assert report["model_inference_performed"] is False


def test_causality_gates_and_tampering():
    docs, source, rendezvous, knowledge = fixture()
    report = propose_npc_knowledge_exchange(
        docs, rendezvous, knowledge, PROMPT, authorized=True,
        expected_source_digest=source)
    assert all(row["source_text"] is None
               for row in report["exchanges"]
               if row["status"] != "delivered_in_sandbox_replay")
    if not report["playable_handoff_allowed"]:
        with pytest.raises(StudioQuestError):
            compile_knowledge_exchange_playable(docs, report, authorized=True)
    for forged in ({**report, "delivered_count": 999},
                   {**report, "release_certified": True},
                   {**report, "source_digest": "0" * 64}):
        with pytest.raises(StudioQuestError):
            replay_npc_knowledge_exchange(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        propose_npc_knowledge_exchange(
            docs, rendezvous, knowledge, PROMPT, authorized=False,
            expected_source_digest=source)


def test_invalid_binding_identity_and_stale_knowledge():
    docs, source, rendezvous, knowledge = fixture()
    if knowledge["reveals"]:
        cue = knowledge["reveals"][0]
        binding = {
            "fact_id": cue["fact_id"],
            "recipient_scene_id": cue["recipient_scene_id"],
            "meeting_id": rendezvous["meetings"][0]["id"],
        }
        for bad in (
            {"bindings": [binding, binding]},
            {"bindings": [{**binding, "meeting_id": "unknown"}]},
            {"bindings": [{**binding, "authorized": True}]},
            {"bindings": [binding] * 65},
        ):
            with pytest.raises(StudioQuestError):
                compile_npc_knowledge_exchange(
                    docs, rendezvous, knowledge, bad, authorized=True,
                    expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        compile_npc_knowledge_exchange(
            docs, rendezvous, {**knowledge, "earned_count": 999},
            {"bindings": []}, authorized=True, expected_source_digest=source)


def test_private_publication_restore_and_symlink(tmp_path):
    docs, source, rendezvous, knowledge = fixture()
    report = propose_npc_knowledge_exchange(
        docs, rendezvous, knowledge, PROMPT, authorized=True,
        expected_source_digest=source)
    saved = publish_npc_knowledge_exchange(
        docs, report, tmp_path, authorized=True)
    assert saved["file_write_performed"]
    path = tmp_path / "npc_knowledge_exchange.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_npc_knowledge_exchange(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_npc_knowledge_exchange(docs, report, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_npc_knowledge_exchange(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_npc_knowledge_exchange(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_typed_jeeves_router_and_cli(capsys):
    from scripts.studio_npc_knowledge_exchange_cli import main
    docs, source, rendezvous, knowledge = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "rendezvous_receipt": rendezvous, "knowledge_receipt": knowledge,
        "prompt": PROMPT,
    }
    direct = execute_npc_knowledge_exchange_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_knowledge_exchange",
         "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert any(item["name"] == "studio_original_npc_knowledge_exchange"
               for item in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--rendezvous", json.dumps(rendezvous),
                 "--knowledge", json.dumps(knowledge), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["exchange"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_knowledge_exchange_tool(request, authorized=False)


def test_offline_editor_import_roundtrip(tmp_path, capsys):
    from hashlib import sha256
    from scripts.studio_npc_knowledge_exchange_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange_editor import (
        EXPORT_SCHEMA, render_npc_exchange_editor,
        load_npc_exchange_editor_export, publish_npc_exchange_editor,
    )
    docs, source, rendezvous, knowledge = fixture()
    report = propose_npc_knowledge_exchange(
        docs, rendezvous, knowledge, PROMPT, authorized=True,
        expected_source_digest=source)
    html, proof = render_npc_exchange_editor(docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert publish_npc_exchange_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_npc_exchange_editor(docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": report["project_id"],
        "source_digest": source, "session_digest": report["session_digest"],
        "rendezvous_digest": report["rendezvous_digest"],
        "knowledge_digest": report["knowledge_digest"],
        "baseline_exchange_digest": report["exchange_digest"],
        "authoring": report["authoring"],
    }
    path = tmp_path / "npc_exchange_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": report["project_id"],
        "expected_source_digest": source,
        "expected_session_digest": report["session_digest"],
        "expected_rendezvous_digest": report["rendezvous_digest"],
        "expected_knowledge_digest": report["knowledge_digest"],
        "expected_baseline_digest": report["exchange_digest"],
    }
    assert load_npc_exchange_editor_export(path, **kwargs) == report["authoring"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--rendezvous", json.dumps(rendezvous),
        "--knowledge", json.dumps(knowledge),
        "--baseline-exchange", json.dumps(report),
        "--import-authoring", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["exchange"] == report
    path.write_text(json.dumps({**record, "knowledge_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_npc_exchange_editor_export(path, **kwargs)
