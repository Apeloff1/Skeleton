"""Original asset production briefs: source replay, custody, editor and Jeeves."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_ecosystem_scene_asset_bindings import (
    compile_scene_asset_bindings,
)
from skeleton.ai.game_builder.studio_original_asset_briefs import (
    PROMPT, compile_original_asset_briefs, propose_original_asset_briefs,
    replay_original_asset_briefs, render_original_asset_briefs_html,
    publish_original_asset_briefs, restore_original_asset_briefs,
)
from skeleton.ai.game_builder.studio_original_asset_briefs_editor import (
    EXPORT_SCHEMA, render_original_asset_briefs_editor,
    publish_original_asset_briefs_editor, load_original_asset_briefs_editor_export,
)
from skeleton.ai.agents.jeeves.studio_original_asset_briefs_tool import (
    REQUEST_SCHEMA, execute_original_asset_briefs_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    visual = _digest(docs["visual"])
    records = docs["visual"].get("jobs") or docs["visual"].get("asset_recipes")
    recipe = records[0]["id"]
    scenes = docs["scene"]["episode_plan"]
    assignments = {
        row["id"]: {
            asset: recipe for asset in row.get("assets", []) +
            row.get("interactive_objects", [])
        } for row in scenes
    }
    bindings = compile_scene_asset_bindings(
        docs, [], assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    return docs, source, visual, bindings


def test_deterministic_original_briefs_and_source_replay():
    docs, source, visual, bindings = fixture()
    report = propose_original_asset_briefs(
        docs, [], bindings, PROMPT, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    assert report == propose_original_asset_briefs(
        docs, [], bindings, PROMPT, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    assert report["brief_count"] == bindings["used_recipe_count"]
    assert report["rights_verified"] is False
    assert report["production_artifact_verified"] is False
    assert replay_original_asset_briefs(docs, report, authorized=True) == report
    html = render_original_asset_briefs_html(docs, report, authorized=True)
    assert b"Content-Security-Policy" in html


def test_authored_briefs_strict_source_and_priority():
    docs, source, visual, bindings = fixture()
    report = propose_original_asset_briefs(
        docs, [], bindings, PROMPT, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    authored = {"briefs": [dict(row) for row in report["authoring"]["briefs"]]}
    authored["briefs"][0]["brief"] = "Original carved-stone scene object."
    authored["briefs"][0]["priority"] = 3
    changed = compile_original_asset_briefs(
        docs, [], bindings, authored, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    assert changed["briefs"][0]["priority"] == 3
    assert changed["asset_brief_digest"] != report["asset_brief_digest"]
    for bad in (
        {"briefs": []},
        {"briefs": authored["briefs"] * 2},
        {"briefs": [{**authored["briefs"][0], "priority": True}]},
        {"briefs": [{**authored["briefs"][0], "platform": "certified_native"}]},
        {"briefs": [{**authored["briefs"][0], "authorized": True}]},
    ):
        with pytest.raises(StudioQuestError):
            compile_original_asset_briefs(
                docs, [], bindings, bad, authorized=True,
                expected_source_digest=source, expected_visual_digest=visual)


def test_forged_receipt_and_authority_fail_closed():
    docs, source, visual, bindings = fixture()
    report = propose_original_asset_briefs(
        docs, [], bindings, PROMPT, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    for forged in (
        {**report, "release_certified": True},
        {**report, "rights_verified": True},
        {**report, "asset_brief_digest": "0" * 64},
        {**report, "binding_digest": "0" * 64},
    ):
        with pytest.raises(StudioQuestError):
            replay_original_asset_briefs(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        propose_original_asset_briefs(
            docs, [], bindings, PROMPT, authorized=False,
            expected_source_digest=source, expected_visual_digest=visual)


def test_private_publication_restore_and_symlink(tmp_path):
    docs, source, visual, bindings = fixture()
    report = propose_original_asset_briefs(
        docs, [], bindings, PROMPT, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    assert publish_original_asset_briefs(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    path = tmp_path / "original_asset_briefs.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_original_asset_briefs(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_original_asset_briefs(docs, report, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_original_asset_briefs(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_original_asset_briefs(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_jeeves_router_and_cli(capsys):
    from scripts.studio_original_asset_briefs_cli import main
    docs, source, visual, bindings = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source,
        "expected_visual_digest": visual, "actions": [],
        "binding_receipt": bindings, "prompt": PROMPT,
    }
    direct = execute_original_asset_briefs_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_asset_briefs", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(row["name"] == "studio_original_asset_briefs"
               for row in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--expected-visual", visual, "--actions", "[]",
                 "--bindings", json.dumps(bindings), "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["asset_briefs"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_original_asset_briefs_tool(request, authorized=False)


def test_offline_editor_export_import(tmp_path, capsys):
    from scripts.studio_original_asset_briefs_cli import main
    docs, source, visual, bindings = fixture()
    report = propose_original_asset_briefs(
        docs, [], bindings, PROMPT, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    html, proof = render_original_asset_briefs_editor(
        docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert publish_original_asset_briefs_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_original_asset_briefs_editor(
            docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "visual_digest": visual,
        "session_digest": report["session_digest"],
        "baseline_asset_brief_digest": report["asset_brief_digest"],
        "authoring": report["authoring"],
    }
    path = tmp_path / "original_asset_briefs_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": PROJECT,
        "expected_source_digest": source, "expected_visual_digest": visual,
        "expected_session_digest": report["session_digest"],
        "expected_baseline_digest": report["asset_brief_digest"],
    }
    assert load_original_asset_briefs_editor_export(path, **kwargs) == report["authoring"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--expected-visual", visual, "--actions", "[]",
        "--bindings", json.dumps(bindings),
        "--baseline-briefs", json.dumps(report),
        "--import-authoring", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["asset_briefs"] == report
    path.write_text(json.dumps({**record, "visual_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_original_asset_briefs_editor_export(path, **kwargs)
