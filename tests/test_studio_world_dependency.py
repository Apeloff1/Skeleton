"""Deterministic regression contracts for source-leased dependency DAGs."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_dependency import (
    SCHEMA, PROMPT, compile_dependency_world_batch,
    replay_dependency_world_batch, execute_dependency_world_batch,
    replay_dependency_execution, render_dependency_world_html,
    publish_dependency_execution, restore_dependency_execution,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import world_tool_catalog

# These requests use a canonical source-backed tool; no external model calls.
from skeleton.ai.game_builder.studio_ecosystem_catalog import list_blueprints


def _graph():
    # Test IDs and dependencies independently of catalog data. Full source
    # integration is exercised by the catalog-backed end-to-end fixture below.
    return {
        "schema": SCHEMA, "prompt": PROMPT,
        "steps": [
            {"id": "first", "depends_on": [], "request": {"tool": "a", "arguments": {}}},
            {"id": "last", "depends_on": ["first"], "request": {"tool": "b", "arguments": {}}},
        ],
    }


def test_stable_topology_and_source_compiler_boundary(monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    calls = []
    def compile_plan(requests, *, authorized, expected_catalog_digest):
        calls.append((requests, authorized, expected_catalog_digest))
        return {
            "catalog_digest": "a" * 64,
            "provenance": {"projects": [{"project_id": "original", "source_digest": "b" * 64}]},
            "plan_digest": "c" * 64,
        }
    monkeypatch.setattr(mod, "compile_world_batch_plan", compile_plan)
    graph = _graph()
    graph["steps"].insert(0, {"id": "independent", "depends_on": [],
                               "request": {"tool": "c", "arguments": {}}})
    receipt = compile_dependency_world_batch(
        graph, authorized=True, expected_catalog_digest="a" * 64)
    assert receipt["execution_order"] == ["independent", "first", "last"]
    assert [r["tool"] for r in calls[-1][0]] == ["c", "a", "b"]
    assert replay_dependency_world_batch(receipt, authorized=True) == receipt
    tampered = deepcopy(receipt)
    tampered["execution_order"].reverse()
    with pytest.raises(StudioQuestError):
        replay_dependency_world_batch(tampered, authorized=True)
    html = render_dependency_world_html(receipt, authorized=True)
    assert b"default-src 'none'" in html
    assert b"first" in html


@pytest.mark.parametrize("mutation", [
    lambda g: g["steps"][1].update(depends_on=["unknown"]),
    lambda g: g["steps"][1].update(depends_on=["last"]),
    lambda g: g["steps"][1].update(depends_on=["first", "first"]),
    lambda g: g["steps"][0].update(id="last"),
    lambda g: g["steps"][0].update(id="../evil"),
    lambda g: g["steps"][0].update(depends_on=["last"]),
    lambda g: g["steps"][0].update(request={"tool": "x", "arguments": {"authorized": True}}),
])
def test_reject_invalid_graph_before_execution(mutation, monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    def compile_plan(*args, **kwargs):
        raise StudioQuestError("downstream compiler rejected untrusted request")
    monkeypatch.setattr(mod, "compile_world_batch_plan", compile_plan)
    graph = _graph()
    mutation(graph)
    with pytest.raises(StudioQuestError):
        compile_dependency_world_batch(graph, authorized=True,
                                       expected_catalog_digest="a" * 64)


def test_cycle_fails_before_tool_invocation(monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    monkeypatch.setattr(mod, "compile_world_batch_plan",
                        lambda *a, **k: pytest.fail("must not compile cycle"))
    graph = _graph()
    graph["steps"][0]["depends_on"] = ["last"]
    with pytest.raises(StudioQuestError, match="cycle"):
        compile_dependency_world_batch(graph, authorized=True,
                                       expected_catalog_digest="a" * 64)


def test_no_implicit_authority():
    with pytest.raises(PermissionError):
        compile_dependency_world_batch(_graph(), authorized=False,
                                       expected_catalog_digest="a" * 64)


def test_oversize_rejected():
    graph = _graph()
    graph["steps"][0]["request"]["arguments"]["padding"] = "x" * (48 * 1024)
    with pytest.raises(StudioQuestError):
        compile_dependency_world_batch(graph, authorized=True,
                                       expected_catalog_digest="a" * 64)


def test_replay_execution_tamper_fails(monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    monkeypatch.setattr(mod, "compile_world_batch_plan", lambda *a, **k: {
        "catalog_digest": "a" * 64, "provenance": {"projects": []},
        "plan_digest": "b" * 64,
    })
    monkeypatch.setattr(mod, "execute_world_batch", lambda *a, **k: {
        "execution_digest": "c" * 64, "completed_count": 2,
    })
    proof = compile_dependency_world_batch(
        _graph(), authorized=True, expected_catalog_digest="a" * 64)
    receipt = execute_dependency_world_batch(proof, authorized=True)
    assert replay_dependency_execution(receipt, authorized=True) == receipt
    receipt["completed_count"] = 99
    with pytest.raises(StudioQuestError):
        replay_dependency_execution(receipt, authorized=True)


def test_private_publication_and_restore(monkeypatch, tmp_path):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    monkeypatch.setattr(mod, "compile_world_batch_plan", lambda *a, **k: {
        "catalog_digest": "a" * 64, "provenance": {"projects": []},
        "plan_digest": "b" * 64,
    })
    monkeypatch.setattr(mod, "execute_world_batch", lambda *a, **k: {
        "execution_digest": "c" * 64, "completed_count": 2,
    })
    proof = compile_dependency_world_batch(
        _graph(), authorized=True, expected_catalog_digest="a" * 64)
    receipt = execute_dependency_world_batch(proof, authorized=True)
    out = tmp_path / "private"
    out.mkdir(mode=0o700)
    published = publish_dependency_execution(receipt, out, authorized=True)
    assert published["file_write_performed"] is True
    assert restore_dependency_execution(
        out, authorized=True, expected_catalog_digest="a" * 64) == receipt
    with pytest.raises(FileExistsError):
        publish_dependency_execution(receipt, out, authorized=True)
    with pytest.raises(StudioQuestError):
        restore_dependency_execution(
            out, authorized=True, expected_catalog_digest="b" * 64)


def _canonical_request():
    from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
    from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
    from skeleton.ai.agents.jeeves.studio_walk_tool import faction_reputation_tool_schema
    project = "studio_arena_fighting_glacial_fjord"
    source = audit_canon_source(read_blueprint(project), authorized=True)["source_digest"]
    descriptor = faction_reputation_tool_schema()
    return {
        "tool": descriptor["name"],
        "arguments": {
            "schema": descriptor["parameters"]["properties"]["schema"]["const"],
            "project_id": project, "expected_source_digest": source,
            "decisions": [],
        },
    }


def test_real_source_replay_router_cli_and_private_restore(tmp_path, capsys):
    from skeleton.ai.agents.jeeves.studio_world_dependency_tool import (
        REQUEST_SCHEMA, execute_world_dependency_tool,
    )
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    from scripts.studio_world_dependency_cli import main
    request = _canonical_request()
    digest = world_tool_catalog()["catalog_digest"]
    graph = {
        "schema": SCHEMA, "prompt": PROMPT,
        "steps": [
            {"id": "source_audit", "depends_on": [], "request": request},
            {"id": "faction_replay", "depends_on": ["source_audit"], "request": request},
        ],
    }
    proof = compile_dependency_world_batch(
        graph, authorized=True, expected_catalog_digest=digest)
    assert proof["execution_order"] == ["source_audit", "faction_replay"]
    execution = execute_dependency_world_batch(proof, authorized=True)
    assert execution["completed_count"] == 2
    assert execution["all_read_only"] is True
    assert execution["release_certified"] is False
    assert replay_dependency_execution(execution, authorized=True) == execution
    typed = {
        "schema": REQUEST_SCHEMA, "expected_catalog_digest": digest,
        "graph": graph,
    }
    direct = execute_world_dependency_tool(typed, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_world_dependency", "arguments": typed},
        authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert main([
        "--expected-catalog", digest, "--graph", json.dumps(graph),
        "--publish", str(private), "--html-sha256",
    ]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli["execution"]["result_digest"] == execution["result_digest"]
    assert cli["publication"]["file_write_performed"] is True
    assert main([
        "--expected-catalog", digest, "--restore", str(private),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["execution"] == execution
    with pytest.raises(PermissionError):
        execute_world_dependency_tool(typed, authorized=False)
    forged = deepcopy(typed)
    forged["graph"]["steps"][1]["request"]["arguments"]["authorized"] = True
    with pytest.raises(StudioQuestError):
        execute_world_dependency_tool(forged, authorized=True)


def test_private_restore_rejects_duplicate_json_and_symlink(tmp_path, monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    monkeypatch.setattr(mod, "compile_world_batch_plan", lambda *a, **k: {
        "catalog_digest": "a" * 64, "provenance": {"projects": []},
        "plan_digest": "b" * 64,
    })
    monkeypatch.setattr(mod, "execute_world_batch", lambda *a, **k: {
        "execution_digest": "c" * 64, "completed_count": 2,
    })
    proof = compile_dependency_world_batch(
        _graph(), authorized=True, expected_catalog_digest="a" * 64)
    execution = execute_dependency_world_batch(proof, authorized=True)
    publish_dependency_execution(execution, tmp_path, authorized=True)
    target = tmp_path / mod.FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_dependency_execution(
            tmp_path, authorized=True, expected_catalog_digest="a" * 64)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_dependency_execution(
            tmp_path, authorized=True, expected_catalog_digest="a" * 64)


def test_offline_dependency_editor_import_and_lease(tmp_path, monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod
    from skeleton.ai.game_builder.studio_world_dependency_editor import (
        EXPORT_SCHEMA, render_dependency_editor, publish_dependency_editor,
        load_dependency_editor_export,
    )
    monkeypatch.setattr(mod, "compile_world_batch_plan", lambda *a, **k: {
        "catalog_digest": "a" * 64,
        "provenance": {"projects": [{"project_id": "source", "source_digest": "b" * 64}]},
        "plan_digest": "c" * 64,
    })
    proof = compile_dependency_world_batch(
        _graph(), authorized=True, expected_catalog_digest="a" * 64)
    html, attestation = render_dependency_editor(proof, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert attestation["baseline_proof_digest"] == proof["proof_digest"]
    assert publish_dependency_editor(proof, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_dependency_editor(proof, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA,
        "catalog_digest": proof["catalog_digest"],
        "baseline_proof_digest": proof["proof_digest"],
        "baseline_graph_digest": proof["graph_digest"],
        "graph": proof["graph"],
    }
    path = tmp_path / "studio_world_dependency_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    assert load_dependency_editor_export(
        path, authorized=True, expected_catalog_digest="a" * 64,
        baseline_proof=proof) == proof["graph"]
    record["baseline_proof_digest"] = "0" * 64
    path.write_text(json.dumps(record))
    with pytest.raises(StudioQuestError, match="stale"):
        load_dependency_editor_export(
            path, authorized=True, expected_catalog_digest="a" * 64,
            baseline_proof=proof)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        load_dependency_editor_export(
            path, authorized=True, expected_catalog_digest="a" * 64,
            baseline_proof=proof)
