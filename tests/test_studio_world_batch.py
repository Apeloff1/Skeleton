"""Bounded read-only Jeeves world batch: typed planning, replay, custody."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    world_tool_catalog, route_world_tool,
)
from skeleton.ai.agents.jeeves.studio_world_batch_tool import (
    REQUEST_SCHEMA, execute_world_batch_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_batch import (
    PROMPT, compile_world_batch_plan, propose_world_batch_plan,
    replay_world_batch_plan, execute_world_batch, replay_world_batch_execution,
    publish_world_batch_execution, restore_world_batch_execution,
    render_world_batch_html,
)
from skeleton.ai.game_builder.studio_world_batch_editor import (
    EXPORT_SCHEMA, render_world_batch_editor, publish_world_batch_editor,
    load_world_batch_editor_export,
)


def fixture():
    catalog = world_tool_catalog()
    # The static catalog is intentionally read-only. No dynamic Python imports.
    assert any(x["name"] == "studio_original_world_batch"
               for x in catalog["tools"])
    # The catalog-only request is source-independent and has no writes.
    # A concrete world-tool request still carries its own source/session lease.
    from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
    from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
    from skeleton.ai.agents.jeeves.studio_walk_tool import canon_proof_tool_schema
    project = "studio_arena_fighting_glacial_fjord"
    docs = read_blueprint(project)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    descriptor = canon_proof_tool_schema()
    schema = descriptor["parameters"]["properties"]["schema"]["const"]
    arguments = {
        "schema": schema, "project_id": project,
        "expected_source_digest": source,
    }
    # Avoid assumptions about optional tool arguments; required fields must be typed.
    request = {"tool": descriptor["name"], "arguments": arguments}
    return catalog["catalog_digest"], request


def test_typed_plan_and_source_replayed_read_only_execution():
    catalog_digest, request = fixture()
    plan = propose_world_batch_plan(
        PROMPT, [request], authorized=True,
        expected_catalog_digest=catalog_digest)
    assert plan == compile_world_batch_plan(
        [request], authorized=True, expected_catalog_digest=catalog_digest)
    assert replay_world_batch_plan(plan, authorized=True) == plan
    execution = execute_world_batch(plan, authorized=True)
    assert execution["completed_count"] == 1
    assert execution["file_write_performed"] is False
    assert execution["release_certified"] is False
    assert replay_world_batch_execution(execution, authorized=True) == execution
    html = render_world_batch_html(execution, authorized=True)
    assert b"Content-Security-Policy" in html


def test_reject_authoring_unknown_schema_and_recursive_batch():
    digest, request = fixture()
    for invalid in (
        [{"tool": "studio_original_world_batch", "arguments": {}}],
        [{"tool": "unknown", "arguments": {}}],
        [{**request, "arguments": {**request["arguments"], "authorized": True}}],
        [{**request, "arguments": {**request["arguments"], "schema": "forged"}}],
        [request] * 9,
    ):
        with pytest.raises(StudioQuestError):
            compile_world_batch_plan(
                invalid, authorized=True, expected_catalog_digest=digest)
    with pytest.raises(PermissionError):
        compile_world_batch_plan(
            [request], authorized=False, expected_catalog_digest=digest)
    with pytest.raises(StudioQuestError):
        compile_world_batch_plan(
            [request], authorized=True, expected_catalog_digest="0" * 64)


def test_plan_and_execution_forgery_fail_closed():
    digest, request = fixture()
    plan = compile_world_batch_plan(
        [request], authorized=True, expected_catalog_digest=digest)
    execution = execute_world_batch(plan, authorized=True)
    for forged in (
        {**plan, "step_count": 99},
        {**plan, "authoring_allowed": True},
        {**plan, "plan_digest": "0" * 64},
    ):
        with pytest.raises(StudioQuestError):
            replay_world_batch_plan(forged, authorized=True)
    for forged in (
        {**execution, "completed_count": 99},
        {**execution, "release_certified": True},
        {**execution, "execution_digest": "0" * 64},
    ):
        with pytest.raises(StudioQuestError):
            replay_world_batch_execution(forged, authorized=True)


def test_private_publication_restore_and_symlink(tmp_path):
    digest, request = fixture()
    plan = compile_world_batch_plan(
        [request], authorized=True, expected_catalog_digest=digest)
    execution = execute_world_batch(plan, authorized=True)
    assert publish_world_batch_execution(
        execution, tmp_path, authorized=True)["file_write_performed"]
    path = tmp_path / "studio_world_batch_execution.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_world_batch_execution(
        tmp_path, authorized=True, expected_catalog_digest=digest) == execution
    with pytest.raises(FileExistsError):
        publish_world_batch_execution(execution, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_world_batch_execution(
            tmp_path, authorized=True, expected_catalog_digest=digest)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_world_batch_execution(
            tmp_path, authorized=True, expected_catalog_digest=digest)


def test_jeeves_router_and_cli(capsys):
    from scripts.studio_world_batch_cli import main
    digest, request = fixture()
    typed = {
        "schema": REQUEST_SCHEMA, "expected_catalog_digest": digest,
        "prompt": PROMPT, "requests": [request],
    }
    direct = execute_world_batch_tool(typed, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_world_batch", "arguments": typed},
        authorized=True)
    assert routed["result"] == direct
    assert main([
        "--expected-catalog", digest, "--prompt",
        "--requests", json.dumps([request]),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["execution"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_world_batch_tool(typed, authorized=False)


def test_offline_editor_import_with_exact_plan_lease(tmp_path):
    from scripts.studio_world_batch_cli import main
    digest, request = fixture()
    plan = compile_world_batch_plan(
        [request], authorized=True, expected_catalog_digest=digest)
    html, proof = render_world_batch_editor(plan, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert publish_world_batch_editor(
        plan, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_world_batch_editor(plan, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "catalog_digest": digest,
        "baseline_plan_digest": plan["plan_digest"],
        "requests": [request],
    }
    path = tmp_path / "studio_world_batch_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_catalog_digest": digest,
        "expected_baseline_plan_digest": plan["plan_digest"],
    }
    assert load_world_batch_editor_export(path, **kwargs) == [request]
    assert main([
        "--expected-catalog", digest, "--baseline-plan", json.dumps(plan),
        "--import-plan", str(path),
    ]) == 0
    path.write_text(json.dumps({**record, "catalog_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_world_batch_editor_export(path, **kwargs)
