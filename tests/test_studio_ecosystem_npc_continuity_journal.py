"""Deterministic canonical NPC continuity journal end-to-end contracts."""
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
    REQUEST_SCHEMA as KNOWLEDGE_SCHEMA, compile_npc_knowledge,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_exchange import (
    compile_npc_knowledge_exchange,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_journal import (
    PROMPT, compile_npc_continuity_journal, propose_npc_continuity_journal,
    replay_npc_continuity_journal, compile_continuity_playable,
    render_npc_continuity_html, publish_npc_continuity_journal,
    restore_npc_continuity_journal,
)
from skeleton.ai.agents.jeeves.studio_npc_continuity_tool import (
    REQUEST_SCHEMA, execute_npc_continuity_tool,
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
    cast = sorted({row["npc_id"] for row in schedule["timeline"]})
    if len(cast) < 2:
        pytest.skip("source has fewer than two NPCs")
    graph = {"edges": [
        {"from_site": a, "to_site": b, "ticks": 0}
        for a in sites for b in sites if a != b
    ]}
    transit = compile_npc_transit(docs, temporal, graph, authorized=True)
    meeting = {
        "id": "continuity", "npc_ids": cast[:2], "site": sites[0],
        "earliest_tick": 0,
        "latest_tick": min(1000000, max(row["end_tick"] for row in
                                      schedule["timeline"]) + 100),
        "duration_ticks": 1,
    }
    rendezvous = compile_npc_rendezvous(
        docs, transit, [meeting], authorized=True,
        expected_source_digest=source)
    knowledge = compile_npc_knowledge(
        docs, [], {"schema": KNOWLEDGE_SCHEMA, "reveals": []},
        authorized=True, expected_source_digest=source)
    exchange = compile_npc_knowledge_exchange(
        docs, rendezvous, knowledge, {"bindings": []},
        authorized=True, expected_source_digest=source)
    return docs, source, exchange


def test_deterministic_prompt_and_replay():
    docs, source, exchange = fixture()
    report = propose_npc_continuity_journal(
        docs, exchange, PROMPT, authorized=True,
        expected_source_digest=source)
    assert report == propose_npc_continuity_journal(
        docs, exchange, PROMPT, authorized=True,
        expected_source_digest=source)
    assert replay_npc_continuity_journal(docs, report, authorized=True) == report
    assert report["scene_count"] > 0
    assert report["event_count"] == len(report["events"])
    assert report["release_certified"] is False
    assert report["native_scene_timing_verified"] is False


def test_source_bound_note_editor_and_no_spoiler():
    docs, source, exchange = fixture()
    report = propose_npc_continuity_journal(
        docs, exchange, PROMPT, authorized=True,
        expected_source_digest=source)
    key = report["events"][0]["event_key"]
    authored = {"notes": [{"event_key": key, "text": "Check scene blocking."}]}
    edited = compile_npc_continuity_journal(
        docs, exchange, authored, authorized=True,
        expected_source_digest=source)
    assert edited["annotated_count"] == 1
    assert sum(bool(row["operator_note"]) for row in edited["events"]) == 1
    html = render_npc_continuity_html(docs, edited, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"Check scene blocking." in html
    assert all(row["text"] is None for row in edited["events"]
               if row["kind"] != "earned_knowledge_exchange")
    assert replay_npc_continuity_journal(docs, edited, authorized=True) == edited


def test_invalid_note_anchors_tamper_and_playable_hold():
    docs, source, exchange = fixture()
    report = propose_npc_continuity_journal(
        docs, exchange, PROMPT, authorized=True,
        expected_source_digest=source)
    key = report["events"][0]["event_key"]
    for bad in (
        {"notes": [{"event_key": "invented", "text": "invalid"}]},
        {"notes": [{"event_key": key, "text": "okay"}] * 2},
        {"notes": [{"event_key": key, "text": "<script>bad</script>\n"}]},
        {"notes": [{"event_key": key, "text": "okay", "authorized": True}]},
        {"notes": [{"event_key": key, "text": "okay"}] * 65},
    ):
        with pytest.raises(StudioQuestError):
            compile_npc_continuity_journal(
                docs, exchange, bad, authorized=True,
                expected_source_digest=source)
    for forged in ({**report, "annotated_count": 99},
                   {**report, "release_certified": True},
                   {**report, "source_digest": "0" * 64}):
        with pytest.raises(StudioQuestError):
            replay_npc_continuity_journal(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        propose_npc_continuity_journal(
            docs, exchange, PROMPT, authorized=False,
            expected_source_digest=source)
    if not report["playable_handoff_allowed"]:
        with pytest.raises(StudioQuestError):
            compile_continuity_playable(docs, report, authorized=True)


def test_private_persistence_restore_and_symlink(tmp_path):
    docs, source, exchange = fixture()
    report = propose_npc_continuity_journal(
        docs, exchange, PROMPT, authorized=True,
        expected_source_digest=source)
    assert publish_npc_continuity_journal(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    path = tmp_path / "npc_continuity_journal.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_npc_continuity_journal(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_npc_continuity_journal(docs, report, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_npc_continuity_journal(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_npc_continuity_journal(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_typed_jeeves_router_and_cli(capsys):
    from scripts.studio_npc_continuity_cli import main
    docs, source, exchange = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "exchange_receipt": exchange, "prompt": PROMPT,
    }
    direct = execute_npc_continuity_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_continuity", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(item["name"] == "studio_original_npc_continuity"
               for item in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--exchange", json.dumps(exchange), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["journal"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_continuity_tool(request, authorized=False)


def test_offline_editor_export_import(tmp_path, capsys):
    from hashlib import sha256
    from scripts.studio_npc_continuity_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_editor import (
        EXPORT_SCHEMA, render_npc_continuity_editor,
        load_npc_continuity_editor_export, publish_npc_continuity_editor,
    )
    docs, source, exchange = fixture()
    report = propose_npc_continuity_journal(
        docs, exchange, PROMPT, authorized=True,
        expected_source_digest=source)
    html, proof = render_npc_continuity_editor(docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert publish_npc_continuity_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_npc_continuity_editor(docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": report["project_id"],
        "source_digest": source, "session_digest": report["session_digest"],
        "exchange_digest": report["exchange_digest"],
        "baseline_journal_digest": report["journal_digest"],
        "authoring": report["authoring"],
    }
    path = tmp_path / "npc_continuity_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": report["project_id"],
        "expected_source_digest": source,
        "expected_session_digest": report["session_digest"],
        "expected_exchange_digest": report["exchange_digest"],
        "expected_baseline_digest": report["journal_digest"],
    }
    assert load_npc_continuity_editor_export(path, **kwargs) == report["authoring"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--exchange", json.dumps(exchange),
        "--baseline-journal", json.dumps(report),
        "--import-authoring", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["journal"] == report
    path.write_text(json.dumps({**record, "exchange_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_npc_continuity_editor_export(path, **kwargs)
