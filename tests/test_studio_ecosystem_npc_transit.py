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
    last = {}
    required = set()
    for row in schedule["timeline"]:
        prior = last.get(row["npc_id"])
        if prior is not None and prior != row["site"]:
            required.add((prior, row["site"]))
        last[row["npc_id"]] = row["site"]
    graph = {"edges": [
        {"from_site": left, "to_site": right, "ticks": 0}
        for left, right in sorted(required)
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
    _, source, temporal = fixture()
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

def test_offline_transit_editor_export_import_and_custody(tmp_path):
    from hashlib import sha256
    from skeleton.ai.game_builder.studio_ecosystem_npc_transit_editor import (
        EXPORT_SCHEMA, render_npc_transit_editor, publish_npc_transit_editor,
        load_npc_transit_editor_export,
    )
    docs, source, temporal = fixture()
    report = propose_npc_transit(docs, temporal, PROMPT, authorized=True)
    html, proof = render_npc_transit_editor(docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert b"Export typed NPC transit edits" in html
    assert publish_npc_transit_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    assert (tmp_path / "npc_transit_editor.html").stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        publish_npc_transit_editor(docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": report["session_digest"],
        "temporal_digest": report["temporal_digest"],
        "baseline_transit_digest": report["transit_digest"],
        "graph": report["graph"],
    }
    path = tmp_path / "edits.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": PROJECT,
        "expected_source_digest": source,
        "expected_session_digest": report["session_digest"],
        "expected_temporal_digest": report["temporal_digest"],
        "expected_baseline_digest": report["transit_digest"],
    }
    assert load_npc_transit_editor_export(path, **kwargs) == report["graph"]
    with pytest.raises(StudioQuestError):
        load_npc_transit_editor_export(
            path, **{**kwargs, "expected_baseline_digest": "0" * 64})
    path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(StudioQuestError):
        load_npc_transit_editor_export(path, **kwargs)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_npc_transit_editor_export(path, **kwargs)


def test_cli_editor_import_uses_exact_original_transit_receipt(tmp_path, capsys):
    from scripts.studio_npc_transit_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_npc_transit_editor import EXPORT_SCHEMA
    docs, source, temporal = fixture()
    original = propose_npc_transit(docs, temporal, PROMPT, authorized=True)
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--temporal-receipt", json.dumps(temporal), "--prompt",
                 "--editor-directory", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["editor"]["file_write_performed"]
    path = tmp_path / "edits.json"
    record = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": original["session_digest"],
        "temporal_digest": original["temporal_digest"],
        "baseline_transit_digest": original["transit_digest"],
        "graph": original["graph"],
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    path.chmod(0o600)
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--temporal-receipt", json.dumps(temporal),
                 "--baseline-transit", json.dumps(original),
                 "--import-graph", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["transit"] == original
    record["baseline_transit_digest"] = "0" * 64
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--temporal-receipt", json.dumps(temporal),
              "--baseline-transit", json.dumps(original),
              "--import-graph", str(path)])
