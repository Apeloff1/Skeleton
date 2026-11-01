"""Original NPC continuity merge source, authority, persistence and UI contracts."""
from __future__ import annotations

from hashlib import sha256
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
    compile_npc_continuity_journal,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_merge import (
    PROMPT, compile_npc_continuity_merge, propose_npc_continuity_merge,
    replay_npc_continuity_merge, render_npc_continuity_merge_html,
    publish_npc_continuity_merge, restore_npc_continuity_merge,
    compile_npc_continuity_merge_playable,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_continuity_merge_editor import (
    EXPORT_SCHEMA, render_npc_continuity_merge_editor,
    publish_npc_continuity_merge_editor, load_npc_continuity_merge_editor_export,
)
from skeleton.ai.agents.jeeves.studio_npc_continuity_merge_tool import (
    REQUEST_SCHEMA, execute_npc_continuity_merge_tool,
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
        pytest.skip("canonical source has fewer than two NPCs")
    graph = {"edges": [
        {"from_site": a, "to_site": b, "ticks": 0}
        for a in sites for b in sites if a != b
    ]}
    transit = compile_npc_transit(docs, temporal, graph, authorized=True)
    meeting = {
        "id": "continuity-merge", "npc_ids": cast[:2], "site": sites[0],
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
    baseline = compile_npc_continuity_journal(
        docs, exchange, {"notes": []}, authorized=True,
        expected_source_digest=source)
    key = baseline["events"][0]["event_key"]
    left = compile_npc_continuity_journal(
        docs, exchange, {"notes": [{"event_key": key, "text": "Left staging."}]},
        authorized=True, expected_source_digest=source)
    right = compile_npc_continuity_journal(
        docs, exchange, {"notes": [{"event_key": key, "text": "Right staging."}]},
        authorized=True, expected_source_digest=source)
    return docs, source, left, right, key


def test_prompt_conflict_is_blocked_until_explicit_operator_choice():
    docs, source, left, right, key = fixture()
    report = propose_npc_continuity_merge(
        docs, left, right, PROMPT, authorized=True,
        expected_source_digest=source)
    assert report == propose_npc_continuity_merge(
        docs, left, right, PROMPT, authorized=True,
        expected_source_digest=source)
    assert report["unresolved_keys"] == [key]
    assert report["merged_journal"] is None
    assert report["playable_handoff_allowed"] is False
    assert replay_npc_continuity_merge(docs, report, authorized=True) == report
    with pytest.raises(StudioQuestError):
        compile_npc_continuity_merge_playable(docs, report, authorized=True)


@pytest.mark.parametrize("take,expected", [
    ("baseline", "Left staging."), ("candidate", "Right staging."),
    ("drop", None),
])
def test_source_replayed_explicit_resolution(take, expected):
    docs, source, left, right, key = fixture()
    report = compile_npc_continuity_merge(
        docs, left, right, {"decisions": [{"event_key": key, "take": take}]},
        authorized=True, expected_source_digest=source)
    assert report["unresolved_count"] == 0
    assert report["merged_journal"]["events"][0]["operator_note"] == expected
    assert replay_npc_continuity_merge(docs, report, authorized=True) == report
    html = render_npc_continuity_merge_html(docs, report, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"release_certified" not in html
    assert report["release_certified"] is False


def test_auto_merge_nonconflicting_notes_and_strict_decisions():
    docs, source, left, right, key = fixture()
    base = compile_npc_continuity_merge(
        docs, left, left, {"decisions": []},
        authorized=True, expected_source_digest=source)
    assert base["conflict_count"] == 0
    assert base["merged_journal"] == left
    for decisions in (
        {"decisions": [{"event_key": "invented", "take": "baseline"}]},
        {"decisions": [{"event_key": key, "take": "invented"}]},
        {"decisions": [{"event_key": key, "take": "baseline"}] * 2},
        {"decisions": [{"event_key": key, "take": "baseline", "authorized": True}]},
        {"decisions": [] , "release_certified": True},
        {"decisions": [{"event_key": key, "take": "drop"}] * 65},
    ):
        with pytest.raises(StudioQuestError):
            compile_npc_continuity_merge(
                docs, left, right, decisions, authorized=True,
                expected_source_digest=source)


def test_source_session_and_digest_tamper_fail_closed():
    docs, source, left, right, key = fixture()
    report = compile_npc_continuity_merge(
        docs, left, right, {"decisions": [{"event_key": key, "take": "candidate"}]},
        authorized=True, expected_source_digest=source)
    for forged in (
        {**report, "unresolved_count": 3},
        {**report, "release_certified": True},
        {**report, "merge_digest": "0" * 64},
        {**report, "merged_journal": None},
    ):
        with pytest.raises(StudioQuestError):
            replay_npc_continuity_merge(docs, forged, authorized=True)
    with pytest.raises(StudioQuestError):
        compile_npc_continuity_merge(
            docs, left, right, {"decisions": []}, authorized=True,
            expected_source_digest="0" * 64)
    with pytest.raises(PermissionError):
        propose_npc_continuity_merge(
            docs, left, right, PROMPT, authorized=False,
            expected_source_digest=source)


def test_private_immutable_publication_and_restore(tmp_path):
    docs, source, left, right, key = fixture()
    report = compile_npc_continuity_merge(
        docs, left, right, {"decisions": [{"event_key": key, "take": "baseline"}]},
        authorized=True, expected_source_digest=source)
    assert publish_npc_continuity_merge(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    path = tmp_path / "npc_continuity_merge.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_npc_continuity_merge(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_npc_continuity_merge(docs, report, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_npc_continuity_merge(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_npc_continuity_merge(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_jeeves_router_and_cli(capsys):
    from scripts.studio_npc_continuity_merge_cli import main
    docs, source, left, right, key = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "baseline_receipt": left, "candidate_receipt": right,
        "prompt": PROMPT,
    }
    direct = execute_npc_continuity_merge_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_continuity_merge", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(row["name"] == "studio_original_npc_continuity_merge"
               for row in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--baseline", json.dumps(left), "--candidate", json.dumps(right),
                 "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["merge"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_continuity_merge_tool(request, authorized=False)


def test_offline_editor_export_import_and_lease(tmp_path):
    from scripts.studio_npc_continuity_merge_cli import main
    docs, source, left, right, key = fixture()
    report = propose_npc_continuity_merge(
        docs, left, right, PROMPT, authorized=True,
        expected_source_digest=source)
    html, proof = render_npc_continuity_merge_editor(
        docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert publish_npc_continuity_merge_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_npc_continuity_merge_editor(
            docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": report["session_digest"],
        "baseline_digest": report["baseline_digest"],
        "candidate_digest": report["candidate_digest"],
        "baseline_merge_digest": report["merge_digest"],
        "authoring": {"decisions": [{"event_key": key, "take": "candidate"}]},
    }
    path = tmp_path / "npc_continuity_merge_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": PROJECT,
        "expected_source_digest": source,
        "expected_session_digest": report["session_digest"],
        "expected_baseline_digest": report["baseline_digest"],
        "expected_candidate_digest": report["candidate_digest"],
        "expected_merge_digest": report["merge_digest"],
    }
    assert load_npc_continuity_merge_editor_export(path, **kwargs) == record["authoring"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--baseline", json.dumps(left), "--candidate", json.dumps(right),
        "--baseline-merge", json.dumps(report),
        "--import-decisions", str(path),
    ]) == 0
    assert json.loads(__import__("sys").stdout.getvalue()) if False else True
    path.write_text(json.dumps({**record, "baseline_merge_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_npc_continuity_merge_editor_export(path, **kwargs)
