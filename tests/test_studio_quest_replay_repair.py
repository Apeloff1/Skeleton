"""Deterministic, bounded quest replay repair with explicit operator selection."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_replay_repair import (
    SCHEMA, APPROVAL_SCHEMA, PROMPT, compile_replay_repair,
    replay_replay_repair, approve_replay_repair, propose_replay_repair,
    render_replay_repair_html,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_replay_repair_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    authoring = {
        "actions": [["not_an_authored_stage", "forged"]],
        "target_ending": program.endings[0][0],
        "expected_final_session_digest": None,
    }
    leases = {
        "authorized": True,
        "expected_source_digest": program.source_digest,
        "expected_initial_session_digest": initial.digest,
    }
    return docs, authoring, leases


def approval(proposal, index=0):
    return {
        "schema": APPROVAL_SCHEMA,
        "proposal_digest": proposal["proposal_digest"],
        "candidate_digest": proposal["candidates"][index]["candidate_digest"],
    }


def test_proposal_replays_legal_prefix_and_operator_selects_repair():
    docs, plan, leases = fixture()
    report = compile_replay_repair(docs, plan, **leases)
    assert report["schema"] == SCHEMA
    assert report["status"] == "candidate_review_required"
    assert report["first_invalid_action"]["index"] == 0
    assert report["candidate_count"] > 1
    assert report["candidates"][0]["repair_kind"] == "truncate_at_first_invalid"
    assert report["candidates"][0]["actions"] == []
    assert report["playable_handoff_allowed"] is False
    assert replay_replay_repair(docs, report, authorized=True) == report
    assert propose_replay_repair(docs, PROMPT, plan, **leases) == report
    repaired = approve_replay_repair(
        docs, report, approval(report, 1), **leases)
    assert repaired["first_invalid_action"] is None
    assert len(repaired["accepted_actions"]) == 1
    assert repaired["release_certified"] is False
    assert repaired["canonical_quest_replay_verified"] is True


@pytest.mark.parametrize("mutation", [
    lambda x: x.update({"proposal_digest": "0" * 64}),
    lambda x: x.update({"candidate_digest": "0" * 64}),
    lambda x: x.update({"schema": "unknown"}),
    lambda x: x.update({"authorized": True}),
    lambda x: x.pop("candidate_digest"),
])
def test_approval_rejects_forged_or_partial_selection(mutation):
    docs, plan, leases = fixture()
    report = compile_replay_repair(docs, plan, **leases)
    selected = approval(report)
    mutation(selected)
    with pytest.raises(StudioQuestError):
        approve_replay_repair(docs, report, selected, **leases)


def test_stale_source_session_forged_receipt_and_unrelated_prompt_fail_closed():
    docs, plan, leases = fixture()
    report = compile_replay_repair(docs, plan, **leases)
    with pytest.raises(PermissionError):
        compile_replay_repair(
            docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        propose_replay_repair(docs, "rewrite the ending", plan, **leases)
    tampered = copy.deepcopy(report)
    tampered["candidates"][0]["target_ending_eligible"] = True
    with pytest.raises(StudioQuestError):
        replay_replay_repair(docs, tampered, authorized=True)
    with pytest.raises(StudioQuestError):
        approve_replay_repair(
            docs, report, approval(report),
            **{**leases, "expected_source_digest": "0" * 64})
    drift = copy.deepcopy(docs)
    source_key = "stage_graph" if drift["quest"].get("stage_graph") else "stages"
    drift["quest"][source_key][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        replay_replay_repair(drift, report, authorized=True)


def test_no_invalid_action_is_not_repairable():
    docs, plan, leases = fixture()
    program = compile_quest_program(docs)
    plan["actions"] = [[program.stages[0].key, program.stages[0].alternatives[0]]]
    with pytest.raises(StudioQuestError, match="requires a first invalid"):
        compile_replay_repair(docs, plan, **leases)


def test_offline_review_csp_and_no_network():
    docs, plan, leases = fixture()
    report = compile_replay_repair(docs, plan, **leases)
    html = render_replay_repair_html(docs, report, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"Export selection" in html
    assert report["proposal_digest"].encode("ascii") in html


def test_typed_jeeves_route_requires_operator_opt_in(monkeypatch):
    docs, plan, leases = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_replay_repair_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_replay_repair"
    entry = next(x for x in world_tool_catalog()["tools"] if x["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT, "authoring": plan,
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"],
    }}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    routed = route_world_tool(request, authorized=True, allow_authoring=True)
    assert routed["result"]["detail"]["candidate_count"] > 1
    assert routed["file_write_performed"] is False


def test_cli_private_approval_and_diagnostic_publication(tmp_path, capsys):
    from scripts.studio_quest_replay_repair_cli import main
    docs, plan, leases = fixture()
    plan_path = tmp_path / "repair.json"
    plan_path.write_text(json.dumps(plan))
    os.chmod(plan_path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(plan_path)]
    assert main(args) == 0
    proposed = json.loads(capsys.readouterr().out)["proposal"]
    assert main(args + ["--review-html"]) == 0
    assert "Quest replay recovery review" in capsys.readouterr().out
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval(proposed, 1)))
    os.chmod(approval_path, 0o600)
    assert main(args + ["--approve", "--approval-file", str(approval_path),
                        "--publish", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["file_write_performed"] is True
    assert result["diagnostic"]["first_invalid_action"] is None
    assert result["release_certified"] is False


def test_cli_never_publishes_without_explicit_approval(tmp_path):
    from scripts.studio_quest_replay_repair_cli import main
    docs, plan, leases = fixture()
    plan_path = tmp_path / "repair.json"
    plan_path.write_text(json.dumps(plan))
    os.chmod(plan_path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(plan_path)]
    with pytest.raises(SystemExit):
        main(args + ["--publish", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(args + ["--approve"])
