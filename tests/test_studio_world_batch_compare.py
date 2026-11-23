"""Original world workflow comparison: source replay, moves, tampering and CLI."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_batch import compile_world_batch_plan
from skeleton.ai.game_builder.studio_world_batch_compare import (
    compare_world_batch_plans, replay_world_batch_comparison,
    render_world_batch_comparison_html,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import world_tool_catalog
from skeleton.ai.agents.jeeves.studio_walk_tool import faction_reputation_tool_schema
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source


def _fixture():
    project = "studio_arena_fighting_glacial_fjord"
    source = audit_canon_source(read_blueprint(project), authorized=True)["source_digest"]
    descriptor = faction_reputation_tool_schema()
    request = {
        "tool": descriptor["name"],
        "arguments": {
            "schema": descriptor["parameters"]["properties"]["schema"]["const"],
            "project_id": project, "expected_source_digest": source,
            "decisions": [],
        },
    }
    return request, world_tool_catalog()["catalog_digest"]


def _plans():
    request, catalog = _fixture()
    second = deepcopy(request)
    second["arguments"]["decisions"] = []
    third = deepcopy(request)
    third["arguments"]["decisions"] = []
    baseline = compile_world_batch_plan(
        [request, second], authorized=True, expected_catalog_digest=catalog)
    candidate = compile_world_batch_plan(
        [second, request, third], authorized=True,
        expected_catalog_digest=catalog)
    return baseline, candidate, catalog


def test_source_replayed_comparison_and_html_are_deterministic():
    baseline, candidate, _ = _plans()
    comparison = compare_world_batch_plans(baseline, candidate, authorized=True)
    assert comparison["candidate_step_count"] == 3
    assert comparison["baseline_step_count"] == 2
    assert comparison["changed_count"] == 1
    assert comparison["added_count"] == 1
    assert comparison["removed_count"] == 0
    assert comparison["release_certified"] is False
    assert comparison["file_write_performed"] is False
    assert replay_world_batch_comparison(
        comparison, baseline, candidate, authorized=True) == comparison
    html = render_world_batch_comparison_html(
        comparison, baseline, candidate, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"Source-verified world workflow changes" in html
    assert sha256(html).hexdigest() == sha256(render_world_batch_comparison_html(
        comparison, baseline, candidate, authorized=True)).hexdigest()


def test_order_changes_are_classified_as_moves_not_authoring():
    request, catalog = _fixture()
    changed = deepcopy(request)
    changed["arguments"]["decisions"] = ["a"]
    left = compile_world_batch_plan([request, changed], authorized=True,
                                    expected_catalog_digest=catalog)
    right = compile_world_batch_plan([changed, request], authorized=True,
                                     expected_catalog_digest=catalog)
    result = compare_world_batch_plans(left, right, authorized=True)
    assert result["moved_count"] == 2
    assert result["added_count"] == 0
    assert result["removed_count"] == 0


def test_tampered_comparison_and_mismatched_source_fail_closed():
    baseline, candidate, _ = _plans()
    receipt = compare_world_batch_plans(baseline, candidate, authorized=True)
    for forged in (
        {**receipt, "changed_count": 999},
        {**receipt, "comparison_digest": "0" * 64},
        {**receipt, "release_certified": True},
        {**receipt, "source_projects": []},
    ):
        with pytest.raises(StudioQuestError):
            replay_world_batch_comparison(
                forged, baseline, candidate, authorized=True)
    with pytest.raises(StudioQuestError):
        compare_world_batch_plans(baseline, {**candidate, "plan_digest": "0" * 64},
                                  authorized=True)
    with pytest.raises(PermissionError):
        compare_world_batch_plans(baseline, candidate, authorized=False)


def test_cli_read_only_comparison(capsys):
    from scripts.studio_world_batch_cli import main
    baseline, candidate, catalog = _plans()
    record = {"baseline": baseline, "candidate": candidate}
    assert main([
        "--expected-catalog", catalog,
        "--compare-plans", json.dumps(record, separators=(",", ":")),
        "--html-sha256",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["comparison"]["changed_count"] == 1
    assert output["file_write_performed"] is False
    assert len(output["html_sha256"]) == 64
