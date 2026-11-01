"""Real quest engine regression proof, custody and operator integrations."""
from __future__ import annotations

from copy import deepcopy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    PLAN_SCHEMA, compile_prompt_quest_plan, publish_prompt_quest_plan,
    revise_prompt_quest_plan,
)
from skeleton.ai.game_builder.studio_quest_regression_matrix import (
    FILENAME, compile_quest_regression_matrix, replay_quest_regression_matrix,
    render_quest_regression_html, publish_quest_regression_matrix,
    restore_quest_regression_matrix,
)


def plan():
    return {
        "schema": PLAN_SCHEMA, "project_id": "coast-lantern",
        "prompt": "Original tide observatory expedition and lighthouse rescue.",
        "originality_attested": True,
        "stages": [
            {"id": "beacon", "prerequisites": [], "alternatives": ["light", "leave"],
             "reward": "signal", "choice_effects": {"light": ["lit"]}},
            {"id": "harbor", "prerequisites": ["beacon"], "alternatives": ["sail"],
             "reward": "arrival", "choice_effects": {}},
        ],
        "endings": [
            {"id": "rescue", "requires": ["lit", "arrival"]},
            {"id": "depart", "requires": ["arrival"]},
        ],
    }


def revisions():
    original = plan()
    before = compile_prompt_quest_plan(
        original, authorized=True, expected_plan_digest=_digest(original))
    after = revise_prompt_quest_plan(
        before, {"kind": "ending_requirements", "id": "rescue",
                 "value": ["unobserved_native_signal"]},
        authorized=True, expected_receipt_digest=before["receipt_digest"])
    return before, after


def matrix(before=None, after=None, **changes):
    if before is None or after is None:
        before, after = revisions()
    kw = {
        "authorized": True, "expected_baseline_digest": before["receipt_digest"],
        "expected_candidate_digest": after["receipt_digest"],
        "max_states": 128, "max_depth": 4,
    }
    kw.update(changes)
    return compile_quest_regression_matrix(before, after, **kw)


def test_real_reachable_ending_regresses_and_unchanged_ending_survives():
    before, after = revisions()
    result = matrix(before, after)
    rows = {row["ending_id"]: row for row in result["rows"]}
    assert result["proven_regressions"] == ["rescue"]
    assert rows["rescue"]["baseline_status"] == "found"
    assert rows["rescue"]["candidate_status"] == "unreachable"
    assert rows["depart"]["baseline_status"] == "found"
    assert rows["depart"]["candidate_status"] == "found"
    assert result["review_required"]
    assert not result["native_gameplay_verified"]
    assert not result["release_certified"]
    assert replay_quest_regression_matrix(
        result, authorized=True,
        expected_baseline_digest=before["receipt_digest"],
        expected_candidate_digest=after["receipt_digest"]) == result


def test_inconclusive_budget_is_not_false_regression():
    before, after = revisions()
    result = matrix(before, after, max_states=1)
    assert result["proven_regressions"] == []
    assert result["uncertain_endings"]
    assert all(not r["regression_proven"] for r in result["rows"])


def test_authorization_tamper_cross_project_and_stale_leases_fail_closed():
    before, after = revisions()
    with pytest.raises(PermissionError):
        matrix(before, after, authorized=False)
    with pytest.raises(StudioQuestError, match="stale"):
        matrix(before, after, expected_candidate_digest="0" * 64)
    other = deepcopy(after)
    other["plan"]["project_id"] = "different"
    with pytest.raises(StudioQuestError):
        matrix(before, other)
    result = matrix(before, after)
    forged = deepcopy(result)
    forged["rows"][0]["regression_proven"] = False
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_quest_regression_matrix(
            forged, authorized=True,
            expected_baseline_digest=before["receipt_digest"],
            expected_candidate_digest=after["receipt_digest"])


def test_private_publication_restore_and_symlink_refusal(tmp_path):
    before, after = revisions()
    result = matrix(before, after)
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    kw = {"authorized": True,
          "expected_baseline_digest": before["receipt_digest"],
          "expected_candidate_digest": after["receipt_digest"]}
    assert publish_quest_regression_matrix(result, directory, **kw)["file_write_performed"]
    assert restore_quest_regression_matrix(directory, **kw) == result
    with pytest.raises(FileExistsError):
        publish_quest_regression_matrix(result, directory, **kw)
    assert b"default-src 'none'" in render_quest_regression_html(result, **kw)
    (directory / FILENAME).unlink()
    (directory / FILENAME).symlink_to(tmp_path / "elsewhere")
    with pytest.raises((OSError, StudioQuestError)):
        restore_quest_regression_matrix(directory, **kw)


def test_cli_and_typed_jeeves_router(tmp_path, capsys):
    from scripts.studio_quest_regression_matrix_cli import main
    from skeleton.ai.agents.jeeves.studio_quest_regression_matrix_tool import (
        REQUEST_SCHEMA, execute_quest_regression_matrix_tool,
    )
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    before, after = revisions()
    first, second = tmp_path / "before", tmp_path / "after"
    first.mkdir(mode=0o700)
    second.mkdir(mode=0o700)
    publish_prompt_quest_plan(before, first, authorized=True)
    publish_prompt_quest_plan(after, second, authorized=True)
    assert main([
        "--baseline-dir", str(first), "--candidate-dir", str(second),
        "--expected-baseline", before["receipt_digest"],
        "--expected-candidate", after["receipt_digest"],
    ]) == 0
    assert json.loads(capsys.readouterr().out)["matrix"]["proven_regressions"] == ["rescue"]
    request = {
        "schema": REQUEST_SCHEMA, "baseline_compilation": before,
        "candidate_compilation": after,
        "expected_baseline_digest": before["receipt_digest"],
        "expected_candidate_digest": after["receipt_digest"],
        "max_states": 128, "max_depth": 4,
    }
    direct = execute_quest_regression_matrix_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_quest_regression_matrix", "arguments": request},
        authorized=True,
    )
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
