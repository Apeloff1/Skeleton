"""Regression coverage for source-bound original world dependency impact."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_dependency import (
    SCHEMA as GRAPH_SCHEMA, PROMPT, compile_dependency_world_batch,
)
from skeleton.ai.game_builder.studio_world_dependency_impact import (
    FILENAME, compile_dependency_impact, replay_dependency_impact,
    render_dependency_impact_html, publish_dependency_impact,
    restore_dependency_impact,
)


def graph():
    return {
        "schema": GRAPH_SCHEMA, "prompt": PROMPT,
        "steps": [
            {"id": "source", "depends_on": [], "request": {"tool": "x", "arguments": {}}},
            {"id": "middle", "depends_on": ["source"], "request": {"tool": "x", "arguments": {}}},
            {"id": "ending", "depends_on": ["middle"], "request": {"tool": "x", "arguments": {}}},
            {"id": "side", "depends_on": [], "request": {"tool": "x", "arguments": {}}},
        ],
    }


@pytest.fixture
def canonical(monkeypatch):
    import skeleton.ai.game_builder.studio_world_dependency as mod

    def compile_plan(requests, *, authorized, expected_catalog_digest):
        assert authorized is True
        return {
            "catalog_digest": expected_catalog_digest,
            "provenance": {"projects": [
                {"project_id": "original", "source_digest": "b" * 64},
            ]},
            "plan_digest": "c" * 64,
        }

    monkeypatch.setattr(mod, "compile_world_batch_plan", compile_plan)
    return compile_dependency_world_batch(
        graph(), authorized=True, expected_catalog_digest="a" * 64,
    )


def test_unchanged_graph_has_no_impact(canonical):
    receipt = compile_dependency_impact(
        canonical, graph(), authorized=True, expected_catalog_digest="a" * 64,
    )
    assert receipt["changes"] == []
    assert receipt["recompile_order"] == []
    assert receipt["change_requires_reverification"] is False
    assert replay_dependency_impact(receipt, authorized=True) == receipt


def test_request_change_invalidates_descendants_but_not_independent(canonical):
    edited = graph()
    edited["steps"][0]["request"]["arguments"]["new"] = "authored"
    receipt = compile_dependency_impact(
        canonical, edited, authorized=True, expected_catalog_digest="a" * 64,
    )
    assert receipt["changed_step_count"] == 1
    assert receipt["impacted_step_ids"] == ["ending", "middle", "source"]
    assert receipt["recompile_order"] == ["source", "middle", "ending"]
    assert "side" not in receipt["recompile_order"]
    assert receipt["changes"][0]["kind"] == "request_changed"
    assert b"default-src 'none'" in render_dependency_impact_html(
        receipt, authorized=True,
    )


def test_removed_step_is_reported_and_invalidates_old_dependents(canonical):
    edited = graph()
    edited["steps"] = [
        step for step in edited["steps"] if step["id"] not in {"middle", "ending"}
    ]
    receipt = compile_dependency_impact(
        canonical, edited, authorized=True, expected_catalog_digest="a" * 64,
    )
    assert receipt["removed_step_ids"] == ["ending", "middle"]
    assert receipt["recompile_order"] == []
    assert receipt["changed_step_count"] == 2


def test_added_dependency_and_request_invalidate_downstream(canonical):
    edited = graph()
    edited["steps"][1]["depends_on"] = ["source", "side"]
    edited["steps"][1]["request"]["arguments"]["revision"] = 1
    receipt = compile_dependency_impact(
        canonical, edited, authorized=True, expected_catalog_digest="a" * 64,
    )
    assert receipt["changes"][0]["kind"] == "request_and_dependencies_changed"
    assert receipt["recompile_order"] == ["middle", "ending"]


def test_tampered_impact_and_unauthorized_access_fail(canonical):
    receipt = compile_dependency_impact(
        canonical, graph(), authorized=True, expected_catalog_digest="a" * 64,
    )
    forged = deepcopy(receipt)
    forged["release_certified"] = True
    with pytest.raises(StudioQuestError, match="replay"):
        replay_dependency_impact(forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_dependency_impact(
            canonical, graph(), authorized=False,
            expected_catalog_digest="a" * 64,
        )
    with pytest.raises(StudioQuestError, match="stale"):
        compile_dependency_impact(
            canonical, graph(), authorized=True,
            expected_catalog_digest="0" * 64,
        )


def test_canonical_source_transplant_is_rejected(monkeypatch, canonical):
    import skeleton.ai.game_builder.studio_world_dependency as mod

    def changed_plan(requests, *, authorized, expected_catalog_digest):
        return {
            "catalog_digest": expected_catalog_digest,
            "provenance": {"projects": [
                {"project_id": "other", "source_digest": "d" * 64},
            ]},
            "plan_digest": "c" * 64,
        }

    # The baseline must still replay: only the candidate compilation drifts.
    previous = mod.compile_world_batch_plan
    calls = 0
    def sequence(*args, **kwargs):
        nonlocal calls
        calls += 1
        return previous(*args, **kwargs) if calls == 1 else changed_plan(*args, **kwargs)
    monkeypatch.setattr(mod, "compile_world_batch_plan", sequence)
    with pytest.raises(StudioQuestError, match="canonical source custody"):
        compile_dependency_impact(
            canonical, graph(), authorized=True, expected_catalog_digest="a" * 64,
        )


def test_private_publication_replay_and_tamper(canonical, tmp_path):
    receipt = compile_dependency_impact(
        canonical, graph(), authorized=True, expected_catalog_digest="a" * 64,
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert publish_dependency_impact(
        receipt, private, authorized=True,
    )["file_write_performed"]
    assert restore_dependency_impact(
        private, authorized=True, expected_catalog_digest="a" * 64,
    ) == receipt
    with pytest.raises(FileExistsError):
        publish_dependency_impact(receipt, private, authorized=True)
    target = private / FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_dependency_impact(
            private, authorized=True, expected_catalog_digest="a" * 64,
        )
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_dependency_impact(
            private, authorized=True, expected_catalog_digest="a" * 64,
        )


def test_cli_and_jeeves_router_parity(canonical, tmp_path, capsys):
    from scripts.studio_world_dependency_impact_cli import main
    from skeleton.ai.agents.jeeves.studio_world_dependency_impact_tool import (
        REQUEST_SCHEMA, execute_world_dependency_impact_tool,
    )
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    edited = graph()
    edited["steps"][0]["request"]["arguments"]["edit"] = "original"
    expected = compile_dependency_impact(
        canonical, edited, authorized=True, expected_catalog_digest="a" * 64,
    )
    assert main([
        "--expected-catalog", "a" * 64, "--baseline-proof", json.dumps(canonical),
        "--candidate-graph", json.dumps(edited), "--publish", str(tmp_path),
        "--html-sha256",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["impact"] == expected
    assert output["publication"]["file_write_performed"] is True
    assert main(["--expected-catalog", "a" * 64, "--restore", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["impact"] == expected
    request = {
        "schema": REQUEST_SCHEMA, "expected_catalog_digest": "a" * 64,
        "baseline_proof": canonical, "candidate_graph": edited,
    }
    direct = execute_world_dependency_impact_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_world_dependency_impact", "arguments": request},
        authorized=True,
    )
    assert routed["result"] == direct
    assert direct["detail"] == expected
    assert routed["file_write_performed"] is False
    with pytest.raises(PermissionError):
        execute_world_dependency_impact_tool(request, authorized=False)
