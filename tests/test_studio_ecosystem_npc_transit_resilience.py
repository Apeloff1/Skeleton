"""Deterministic NPC disruption, fallback, custody and typed end-user integration."""
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
from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience import (
    PROMPT, compile_npc_transit_resilience, propose_npc_transit_resilience,
    replay_npc_transit_resilience, select_npc_transit_fallback,
    publish_npc_transit_resilience, restore_npc_transit_resilience,
)
from skeleton.ai.agents.jeeves.studio_npc_transit_resilience_tool import (
    REQUEST_SCHEMA, execute_npc_transit_resilience_tool,
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
    # The directed edges are explicit operator estimates, not physical travel.
    from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import compile_scene_schedule
    schedule = compile_scene_schedule(
        docs, [], temporal["authoring"]["schedule_request"], authorized=True,
        expected_source_digest=source)
    sites = sorted({row["site"] for row in schedule["timeline"]})
    graph = {"edges": [
        {"from_site": left, "to_site": right, "ticks": 0}
        for left in sites for right in sites if left != right
    ]}
    baseline = compile_npc_transit(docs, temporal, graph, authorized=True)
    return docs, source, baseline


def test_deterministic_outages_replay_and_honest_coverage():
    docs, source, baseline = fixture()
    report = propose_npc_transit_resilience(
        docs, baseline, PROMPT, authorized=True, expected_source_digest=source)
    assert report == propose_npc_transit_resilience(
        docs, baseline, PROMPT, authorized=True, expected_source_digest=source)
    assert replay_npc_transit_resilience(docs, report, authorized=True) == report
    assert report["tested_variant_count"] <= 12
    assert report["physical_travel_verified"] is False
    assert report["model_inference_performed"] is False
    assert report["complete_disruption_coverage"] == (
        report["total_directed_edges"] == report["tested_variant_count"]
        if report["total_directed_edges"] else False
    )


def test_blocked_route_cannot_be_selected_or_played():
    docs, source, baseline = fixture()
    if not baseline["graph"]["edges"]:
        pytest.skip("source contains only one transit site")
    edge = baseline["graph"]["edges"][0]
    variant = [{"id": "one-outage", "closed_edges": [
        {"from_site": edge["from_site"], "to_site": edge["to_site"]}]}]
    report = compile_npc_transit_resilience(
        docs, baseline, variant, authorized=True, expected_source_digest=source)
    assert report["outcomes"][0]["fallback_transit_digest"]
    if report["outcomes"][0]["status"] == "blocked":
        with pytest.raises(StudioQuestError):
            select_npc_transit_fallback(
                docs, report, "one-outage", authorized=True, playable=True)
    else:
        selected = select_npc_transit_fallback(
            docs, report, "one-outage", authorized=True, playable=True)
        assert selected["playable_manifest"]["canonical_html5_quest_included"]
        assert selected["physical_travel_verified"] is False


def test_duplicate_unknown_invalid_closures_and_tamper_rejected():
    docs, source, baseline = fixture()
    valid = propose_npc_transit_resilience(
        docs, baseline, PROMPT, authorized=True, expected_source_digest=source)
    for invalid in (
        [{"id": "UPPER", "closed_edges": []}],
        [{"id": "dup", "closed_edges": []}] * 2,
        [{"id": "unknown", "closed_edges": [
            {"from_site": "never", "to_site": "known"}]}],
        [{"id": "wrong", "closed_edges": "invalid"}],
        [{"id": "x", "closed_edges": []}] * 13,
    ):
        with pytest.raises(StudioQuestError):
            compile_npc_transit_resilience(
                docs, baseline, invalid, authorized=True,
                expected_source_digest=source)
    for forged in ({**valid, "release_certified": True},
                   {**valid, "accepted_count": 999},
                   {**valid, "source_digest": "0" * 64}):
        with pytest.raises(StudioQuestError):
            replay_npc_transit_resilience(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        propose_npc_transit_resilience(
            docs, baseline, PROMPT, authorized=False,
            expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        select_npc_transit_fallback(docs, valid, "not-listed", authorized=True)


def test_private_publication_restore_nooverwrite_and_symlink(tmp_path):
    docs, source, baseline = fixture()
    report = propose_npc_transit_resilience(
        docs, baseline, PROMPT, authorized=True, expected_source_digest=source)
    saved = publish_npc_transit_resilience(docs, report, tmp_path, authorized=True)
    assert saved["file_write_performed"] is True
    target = tmp_path / "npc_transit_resilience.json"
    assert target.stat().st_mode & 0o077 == 0
    assert restore_npc_transit_resilience(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_npc_transit_resilience(docs, report, tmp_path, authorized=True)
    target.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_npc_transit_resilience(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_npc_transit_resilience(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_cli_and_jeeves_router(capsys):
    from scripts.studio_npc_transit_resilience_cli import main
    docs, source, baseline = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "baseline_receipt": baseline,
        "prompt": PROMPT,
    }
    direct = execute_npc_transit_resilience_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_transit_resilience", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(x["name"] == "studio_original_npc_transit_resilience"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--baseline-transit", json.dumps(baseline), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["resilience"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_transit_resilience_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_npc_transit_resilience_tool(
            {**request, "authorized": True}, authorized=True)


def test_offline_editor_private_export_import_and_cli_roundtrip(tmp_path, capsys):
    from hashlib import sha256
    from skeleton.ai.game_builder.studio_ecosystem_npc_transit_resilience_editor import (
        EXPORT_SCHEMA, render_npc_resilience_editor,
        load_npc_resilience_editor_export, publish_npc_resilience_editor,
    )
    from scripts.studio_npc_transit_resilience_cli import main
    docs, source, baseline = fixture()
    report = propose_npc_transit_resilience(
        docs, baseline, PROMPT, authorized=True, expected_source_digest=source)
    html, proof = render_npc_resilience_editor(docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert b"Export typed NPC disruption edits" in html
    published = publish_npc_resilience_editor(docs, report, tmp_path, authorized=True)
    assert published["file_write_performed"]
    assert (tmp_path / "npc_transit_resilience_editor.html").stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        publish_npc_resilience_editor(docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": report["project_id"],
        "source_digest": source, "session_digest": report["session_digest"],
        "temporal_digest": report["temporal_digest"],
        "baseline_transit_digest": report["baseline_transit_digest"],
        "baseline_resilience_digest": report["resilience_digest"],
        "variants": report["variants"],
    }
    path = tmp_path / "npc_resilience_variants.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": report["project_id"],
        "expected_source_digest": source,
        "expected_session_digest": report["session_digest"],
        "expected_temporal_digest": report["temporal_digest"],
        "expected_transit_digest": report["baseline_transit_digest"],
        "expected_resilience_digest": report["resilience_digest"],
    }
    assert load_npc_resilience_editor_export(path, **kwargs) == report["variants"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--baseline-transit", json.dumps(baseline),
        "--baseline-resilience", json.dumps(report),
        "--import-variants", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["resilience"] == report
    path.write_text(json.dumps({**record, "source_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_npc_resilience_editor_export(path, **kwargs)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        load_npc_resilience_editor_export(path, **kwargs)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_npc_resilience_editor_export(path, **kwargs)
