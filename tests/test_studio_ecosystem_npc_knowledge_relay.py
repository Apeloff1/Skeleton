"""Source, time, authoring, replay and private custody regressions for NPC relay."""
from __future__ import annotations

import json
import os
from pathlib import Path

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
    PROMPT, SCHEMA, compile_npc_knowledge_relay, propose_npc_knowledge_relay,
    replay_npc_knowledge_relay, compile_npc_relay_playable,
    publish_npc_knowledge_relay, restore_npc_knowledge_relay,
)
from skeleton.ai.agents.jeeves.studio_npc_knowledge_relay_tool import (
    REQUEST_SCHEMA, execute_npc_knowledge_relay_tool,
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
            "id": "relay_meeting", "npc_ids": cast[:2], "site": sites[0],
            "earliest_tick": 0, "latest_tick": min(
                1000000, max(row["end_tick"] for row in
                             schedule["timeline"]) + 100),
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
    return docs, source, exchange


def test_prompt_to_typed_replay_and_no_unearned_handoff():
    docs, source, exchange = fixture()
    result = propose_npc_knowledge_relay(
        docs, exchange, PROMPT, authorized=True, expected_source_digest=source)
    assert result["schema"] == SCHEMA
    assert result == propose_npc_knowledge_relay(
        docs, exchange, PROMPT, authorized=True, expected_source_digest=source)
    assert replay_npc_knowledge_relay(docs, result, authorized=True) == result
    assert result["npc_speech_verified"] is False
    assert result["native_npc_memory_verified"] is False
    assert result["release_certified"] is False
    assert all(row["source_text"] is None for row in result["routes"]
               if row["status"] != "delivered_in_sandbox_replay")
    if not result["playable_handoff_allowed"]:
        with pytest.raises(StudioQuestError):
            compile_npc_relay_playable(docs, result, authorized=True)


def test_untrusted_authoring_and_forged_receipts_fail_closed():
    docs, source, exchange = fixture()
    for bad in (
        {"routes": [1]},
        {"routes": [{}]},
        {"routes": [], "authorized": True},
        {"routes": [dict(fact_id="fact", recipient_scene_id="scene",
                         target_scene_id="target", hops=[])]},
        {"routes": [dict(fact_id="fact", recipient_scene_id="scene",
                         target_scene_id="target",
                         hops=[{"meeting_id": "a", "to_npc_id": "b"}])]},
        {"routes": []} | {"routes": "wrong"},
    ):
        with pytest.raises(StudioQuestError):
            compile_npc_knowledge_relay(
                docs, exchange, bad, authorized=True,
                expected_source_digest=source)
    with pytest.raises(PermissionError):
        compile_npc_knowledge_relay(
            docs, exchange, {"routes": []}, authorized=False,
            expected_source_digest=source)
    valid = compile_npc_knowledge_relay(
        docs, exchange, {"routes": []}, authorized=True,
        expected_source_digest=source)
    for forged in ({**valid, "release_certified": True},
                   {**valid, "delivered_count": 999},
                   {**valid, "source_digest": "0" * 64}):
        with pytest.raises(StudioQuestError):
            replay_npc_knowledge_relay(docs, forged, authorized=True)
    with pytest.raises(StudioQuestError):
        compile_npc_knowledge_relay(
            docs, exchange, {"routes": []}, authorized=True,
            expected_source_digest="0" * 64)


def test_private_immutable_publication_restore_and_symlink(tmp_path):
    docs, source, exchange = fixture()
    valid = compile_npc_knowledge_relay(
        docs, exchange, {"routes": []}, authorized=True,
        expected_source_digest=source)
    saved = publish_npc_knowledge_relay(
        docs, valid, tmp_path, authorized=True)
    assert saved["file_write_performed"] is True
    path = tmp_path / "npc_knowledge_relay.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_npc_knowledge_relay(
        docs, tmp_path, authorized=True, expected_source_digest=source) == valid
    with pytest.raises(FileExistsError):
        publish_npc_knowledge_relay(docs, valid, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_npc_knowledge_relay(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "absent")
    with pytest.raises(OSError):
        restore_npc_knowledge_relay(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_typed_jeeves_router_and_private_cli(tmp_path, capsys):
    from scripts.studio_npc_knowledge_relay_cli import main
    docs, source, exchange = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "exchange_receipt": exchange, "prompt": PROMPT,
    }
    direct = execute_npc_knowledge_relay_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_knowledge_relay",
         "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert any(item["name"] == "studio_original_npc_knowledge_relay"
               for item in world_tool_catalog()["tools"])
    assert direct["detail"]["relay_digest"]
    exchange_file = tmp_path / "exchange.json"
    exchange_file.write_text(json.dumps(exchange))
    exchange_file.chmod(0o600)
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--exchange-file", str(exchange_file), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["relay"] == direct["detail"]
    authored = tmp_path / "authoring.json"
    authored.write_text('{"routes":[]}')
    authored.chmod(0o600)
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--exchange-file", str(exchange_file),
                 "--authoring-file", str(authored), "--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--restore", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["relay"]["authoring"] == {"routes": []}
    authored.write_text('{"routes":[],"routes":[]}')
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--exchange-file", str(exchange_file),
              "--authoring-file", str(authored)])
    with pytest.raises(PermissionError):
        execute_npc_knowledge_relay_tool(request, authorized=False)


def test_offline_csp_editor_export_import_recompiles_source(tmp_path, capsys):
    from hashlib import sha256
    from scripts.studio_npc_knowledge_relay_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_relay_editor import (
        EXPORT_SCHEMA, render_npc_relay_editor, publish_npc_relay_editor,
        load_npc_relay_editor_export,
    )
    docs, source, exchange = fixture()
    relay = compile_npc_knowledge_relay(
        docs, exchange, {"routes": []}, authorized=True,
        expected_source_digest=source)
    html, proof = render_npc_relay_editor(docs, relay, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert b"connect-src 'none'" in html
    assert publish_npc_relay_editor(
        docs, relay, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_npc_relay_editor(docs, relay, tmp_path, authorized=True)
    export = {
        "schema": EXPORT_SCHEMA, "project_id": relay["project_id"],
        "source_digest": source, "session_digest": relay["session_digest"],
        "exchange_digest": relay["exchange_digest"],
        "baseline_relay_digest": relay["relay_digest"],
        "authoring": relay["authoring"],
    }
    edit = tmp_path / "npc_relay_edit.json"
    edit.write_text(json.dumps(export))
    edit.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": PROJECT,
        "expected_source_digest": source,
        "expected_session_digest": relay["session_digest"],
        "expected_exchange_digest": relay["exchange_digest"],
        "expected_baseline_digest": relay["relay_digest"],
    }
    assert load_npc_relay_editor_export(edit, **kwargs) == {"routes": []}
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(relay))
    baseline.chmod(0o600)
    exchange_file = tmp_path / "exchange.json"
    exchange_file.write_text(json.dumps(exchange))
    exchange_file.chmod(0o600)
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--exchange-file", str(exchange_file),
        "--editor-export-file", str(edit),
        "--baseline-relay-file", str(baseline),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["relay"] == relay
    edit.write_text(json.dumps({**export, "baseline_relay_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_npc_relay_editor_export(edit, **kwargs)
    edit.unlink()
    edit.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_npc_relay_editor_export(edit, **kwargs)
