"""Canonical pacing: typed proposal, replay, private custody, UI and CLI."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest, step_quest,
)
from skeleton.ai.game_builder.studio_quest_pacing import (
    PROMPT, PLAN_SCHEMA, FILENAME, propose_quest_pacing,
    compile_quest_pacing, replay_quest_pacing, compile_pacing_handoff,
    publish_quest_pacing, restore_quest_pacing, render_pacing_editor_html,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_pacing_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    stage = program.stages[0]
    action = [stage.key, stage.alternatives[0]]
    advanced = step_quest(initial, docs, stage=action[0],
                          alternative=action[1], authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_quest_pacing(
        docs, PROMPT, [action], target_ending=program.endings[0][0], **leases)
    return docs, plan, leases, advanced


def test_unreviewed_estimates_never_claim_runtime_or_handoff():
    docs, plan, leases, advanced = fixture()
    assert plan["schema"] == PLAN_SCHEMA
    assert all(row["reviewed"] is False for row in plan["beats"])
    receipt = compile_quest_pacing(docs, plan, **leases)
    assert receipt["session_digest"] == advanced.digest
    assert receipt["estimated_play_seconds"] == 90
    assert receipt["duration_is_author_estimate"] is True
    assert receipt["measured_runtime_verified"] is False
    assert receipt["playable_handoff_allowed"] is False
    assert replay_quest_pacing(docs, receipt, authorized=True) == receipt
    with pytest.raises(StudioQuestError):
        compile_pacing_handoff(docs, receipt, authorized=True)


def test_reviewed_budget_and_eligible_ending_guard():
    docs, plan, leases, _ = fixture()
    plan["beats"][0]["reviewed"] = True
    receipt = compile_quest_pacing(docs, plan, **leases)
    assert receipt["played_beats_reviewed"] is True
    assert receipt["within_estimated_budget"] is True
    assert receipt["playable_handoff_allowed"] == receipt["target_ending_eligible"]
    if receipt["playable_handoff_allowed"]:
        handoff = compile_pacing_handoff(docs, receipt, authorized=True)
        assert handoff["timeline"][0]["start_seconds"] == 0
        assert handoff["timeline"][0]["end_seconds"] == 90
        assert handoff["native_gameplay_verified"] is False
    else:
        with pytest.raises(StudioQuestError):
            compile_pacing_handoff(docs, receipt, authorized=True)


def test_over_budget_refuses_handoff_without_forging_time():
    docs, plan, leases, _ = fixture()
    plan["beats"][0]["reviewed"] = True
    plan["beats"][0]["estimated_seconds"] = 361
    plan["budget_seconds"] = 360
    receipt = compile_quest_pacing(docs, plan, **leases)
    assert receipt["within_estimated_budget"] is False
    assert receipt["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_pacing_handoff(docs, receipt, authorized=True)


@pytest.mark.parametrize("mutation", [
    lambda p: p["beats"].pop(),
    lambda p: p["beats"].reverse(),
    lambda p: p["beats"][0].update({"stage_id": "forged"}),
    lambda p: p["beats"][0].update({"reviewed": 1}),
    lambda p: p["beats"][0].update({"estimated_seconds": True}),
    lambda p: p["beats"][0].update({"estimated_seconds": 0}),
    lambda p: p["beats"][0].update({"intensity": 6}),
    lambda p: p["beats"][0].update({"label": "\u202eunsafe"}),
    lambda p: p["beats"][0].update({"note": "x" * 513}),
    lambda p: p.update({"budget_seconds": "3600"}),
    lambda p: p.update({"authorized": True}),
    lambda p: p.update({"target_ending": "not_authored"}),
])
def test_malformed_or_forged_pacing_fails_closed(mutation):
    docs, plan, leases, _ = fixture()
    bad = copy.deepcopy(plan)
    mutation(bad)
    with pytest.raises(StudioQuestError):
        compile_quest_pacing(docs, bad, **leases)


def test_stale_source_and_receipt_tamper():
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_pacing(docs, plan, **leases)
    forged = copy.deepcopy(receipt)
    forged["played_beats_reviewed"] = True
    with pytest.raises(StudioQuestError):
        replay_quest_pacing(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_pacing(docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        compile_quest_pacing(
            docs, plan, **{**leases, "expected_source_digest": "0" * 64})
    with pytest.raises(StudioQuestError):
        propose_quest_pacing(
            docs, "invent runtime measurements", plan["actions"],
            target_ending=plan["target_ending"], **leases)


def test_html_escapes_and_csp_blocks_network():
    docs, plan, leases, _ = fixture()
    plan["beats"][0]["note"] = '</script><img src=x onerror=alert(1)>'
    receipt = compile_quest_pacing(docs, plan, **leases)
    html = render_pacing_editor_html(docs, receipt, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"nonce-" in html
    assert b"&lt;/script&gt;" in html
    assert b"\\u003c" in html
    assert b"</script><img" not in html


def test_private_publish_restore_no_clobber_and_symlink(tmp_path):
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_pacing(docs, plan, **leases)
    result = publish_quest_pacing(docs, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_quest_pacing(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_pacing(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_pacing(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_router_requires_explicit_authoring_permission(monkeypatch):
    docs, plan, leases, _ = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_pacing_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_pacing"
    entry = next(x for x in world_tool_catalog()["tools"] if x["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "actions": plan["actions"], "target_ending": plan["target_ending"],
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"]}}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    result = route_world_tool(request, authorized=True, allow_authoring=True)
    assert result["result"]["detail"] == plan
    assert result["file_write_performed"] is False


def test_cli_plan_editor_publish_restore(tmp_path, capsys):
    from scripts.studio_quest_pacing_cli import main
    docs, plan, leases, _ = fixture()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["pacing"]["estimated_play_seconds"] == 90
    assert main(args + ["--editor-html"]) == 0
    assert "Original quest pacing editor" in capsys.readouterr().out
    assert main(args + ["--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert main(["--project", PROJECT, "--expected-source",
                 leases["expected_source_digest"], "--expected-session",
                 leases["expected_initial_session_digest"], "--restore",
                 str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["pacing"]["session_digest"]
