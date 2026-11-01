"""End-to-end source-bound temporal scenario regression and negative custody."""
from __future__ import annotations

import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    PROMPT as WINDOW_PROMPT, propose_temporal_windows,
)
from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios import (
    PROMPT, compile_temporal_scenarios, propose_temporal_scenarios,
    replay_temporal_scenarios, select_temporal_scenario,
    publish_temporal_scenarios, restore_temporal_scenarios,
)
from skeleton.ai.agents.jeeves.studio_temporal_scenarios_tool import (
    REQUEST_SCHEMA, execute_temporal_scenarios_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    proposal = propose_temporal_windows(
        docs, [], WINDOW_PROMPT, authorized=True,
        expected_source_digest=source)
    return docs, source, proposal["authoring"]


def test_proposal_determinism_replay_and_playable_handoff():
    docs, source, baseline = fixture()
    report = propose_temporal_scenarios(
        docs, [], baseline, PROMPT, authorized=True,
        expected_source_digest=source)
    assert report == propose_temporal_scenarios(
        docs, [], baseline, PROMPT, authorized=True,
        expected_source_digest=source)
    assert report == replay_temporal_scenarios(docs, report, authorized=True)
    assert report["accepted_count"] == 2
    assert report["rejected_count"] == 0
    assert report["native_time_verified"] is False
    selected = select_temporal_scenario(
        docs, report, "tight-deadlines", authorized=True, playable=True)
    assert selected["temporal"]["source_digest"] == source
    assert selected["playable_manifest"]["canonical_html5_quest_included"] is True
    assert selected["release_certified"] is False


def test_rejected_candidate_cannot_be_selected_or_played():
    docs, source, baseline = fixture()
    impossible = json.loads(json.dumps(baseline))
    first = next(iter(impossible["windows"]))
    impossible["windows"][first]["latest"] = 0
    report = compile_temporal_scenarios(
        docs, [], baseline, [{"id": "impossible", "authoring": impossible}],
        authorized=True, expected_source_digest=source)
    assert report["rejected_count"] == 1
    assert report["outcomes"][0]["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        select_temporal_scenario(
            docs, report, "impossible", authorized=True, playable=True)
    with pytest.raises(StudioQuestError):
        select_temporal_scenario(docs, report, "missing", authorized=True)


def test_strict_types_budgets_authorization_and_tamper():
    docs, source, baseline = fixture()
    with pytest.raises(PermissionError):
        propose_temporal_scenarios(
            docs, [], baseline, PROMPT, authorized=False,
            expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        propose_temporal_scenarios(
            docs, [], baseline, "invent evidence", authorized=True,
            expected_source_digest=source)
    for invalid in ([{"id": "A", "authoring": baseline}],
                    [{"id": "x", "authoring": baseline}] * 2,
                    [{"id": "x", "authoring": baseline}] * 13):
        with pytest.raises(StudioQuestError):
            compile_temporal_scenarios(
                docs, [], baseline, invalid, authorized=True,
                expected_source_digest=source)
    report = propose_temporal_scenarios(
        docs, [], baseline, PROMPT, authorized=True,
        expected_source_digest=source)
    for forged in ({**report, "release_certified": True},
                   {**report, "accepted_count": 99},
                   {**report, "source_digest": "0" * 64}):
        with pytest.raises(StudioQuestError):
            replay_temporal_scenarios(docs, forged, authorized=True)


def test_private_atomic_publication_restore_and_symlink(tmp_path):
    docs, source, baseline = fixture()
    report = propose_temporal_scenarios(
        docs, [], baseline, PROMPT, authorized=True,
        expected_source_digest=source)
    saved = publish_temporal_scenarios(
        docs, report, tmp_path, authorized=True)
    assert saved["file_write_performed"] is True
    path = tmp_path / "temporal_scenarios.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_temporal_scenarios(
        docs, tmp_path, authorized=True,
        expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_temporal_scenarios(docs, report, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_temporal_scenarios(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_temporal_scenarios(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_cli_and_typed_jeeves_router(capsys):
    from scripts.studio_temporal_scenarios_cli import main
    docs, source, baseline = fixture()
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--baseline-authoring", json.dumps(baseline), "--prompt",
                 "--select", "buffered-deadlines",
                 "--playable-manifest"]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["selection"]["playable_manifest"]["canonical_html5_quest_included"]
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "actions": [],
        "baseline_authoring": baseline, "prompt": PROMPT,
        "select": "tight-deadlines",
    }
    direct = execute_temporal_scenarios_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_temporal_scenarios", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(x["name"] == "studio_original_temporal_scenarios"
               for x in world_tool_catalog()["tools"])
    with pytest.raises(PermissionError):
        execute_temporal_scenarios_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_temporal_scenarios_tool({**request, "authorized": True},
                                        authorized=True)

def test_editor_render_import_replay_and_private_custody(tmp_path):
    from hashlib import sha256
    from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios_editor import (
        EXPORT_SCHEMA, render_temporal_scenarios_editor,
        load_temporal_scenarios_editor_export, publish_temporal_scenarios_editor,
    )
    docs, source, baseline = fixture()
    report = propose_temporal_scenarios(
        docs, [], baseline, PROMPT, authorized=True,
        expected_source_digest=source)
    html, proof = render_temporal_scenarios_editor(
        docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert b"Export typed scenario edits" in html
    assert publish_temporal_scenarios_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    assert (tmp_path / "temporal_scenarios_editor.html").stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        publish_temporal_scenarios_editor(
            docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": report["project_id"],
        "source_digest": source, "session_digest": report["session_digest"],
        "baseline_scenario_digest": report["scenario_digest"],
        "candidates": report["candidates"],
    }
    path = tmp_path / "edits.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    path.chmod(0o600)
    kwargs = {"authorized": True, "expected_project_id": report["project_id"],
              "expected_source_digest": source,
              "expected_session_digest": report["session_digest"],
              "expected_baseline_digest": report["scenario_digest"]}
    assert load_temporal_scenarios_editor_export(path, **kwargs) == report["candidates"]
    with pytest.raises(StudioQuestError):
        load_temporal_scenarios_editor_export(
            path, **{**kwargs, "expected_baseline_digest": "0" * 64})
    path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(StudioQuestError):
        load_temporal_scenarios_editor_export(path, **kwargs)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_temporal_scenarios_editor_export(path, **kwargs)


def test_cli_editor_import_requires_exact_original_scenario_lease(tmp_path, capsys):
    from scripts.studio_temporal_scenarios_cli import main
    from skeleton.ai.game_builder.studio_ecosystem_temporal_scenarios_editor import EXPORT_SCHEMA
    docs, source, baseline = fixture()
    original = propose_temporal_scenarios(
        docs, [], baseline, PROMPT, authorized=True,
        expected_source_digest=source)
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--baseline-authoring", json.dumps(baseline), "--prompt",
                 "--editor-directory", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["editor"]["file_write_performed"]
    path = tmp_path / "edits.json"
    path.write_text(json.dumps({
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": original["session_digest"],
        "baseline_scenario_digest": original["scenario_digest"],
        "candidates": original["candidates"],
    }), encoding="utf-8")
    path.chmod(0o600)
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--baseline-authoring", json.dumps(baseline),
                 "--baseline-scenarios", json.dumps(original),
                 "--import-candidates", str(path), "--select", "tight-deadlines"]) == 0
    assert json.loads(capsys.readouterr().out)["scenarios"] == original
    path.write_text(json.dumps({
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": original["session_digest"],
        "baseline_scenario_digest": "0" * 64,
        "candidates": original["candidates"],
    }), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--baseline-authoring", json.dumps(baseline),
              "--baseline-scenarios", json.dumps(original),
              "--import-candidates", str(path)])
