"""Advisory review and player consent are distinct, source-replayed contracts."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_advisories import (
    PROMPT, PLAN_SCHEMA, FILENAME, propose_quest_advisories,
    compile_quest_advisories, replay_quest_advisories,
    compile_advisory_handoff, evaluate_player_advisories,
    publish_quest_advisories, restore_quest_advisories,
    render_advisory_editor_html,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_advisories_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    stage = program.stages[0]
    action = [stage.key, stage.alternatives[0]]
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_quest_advisories(
        docs, PROMPT, [action], target_ending=program.endings[0][0], **leases)
    return docs, plan, leases


def test_unreviewed_advisories_cannot_infer_safety_or_handoff():
    docs, plan, leases = fixture()
    assert plan["schema"] == PLAN_SCHEMA
    assert all(not x["reviewed"] for x in plan["advisories"])
    receipt = compile_quest_advisories(docs, plan, **leases)
    assert receipt["content_safety_inferred"] is False
    assert receipt["player_consent_granted"] is False
    assert receipt["all_stages_reviewed"] is False
    assert receipt["advisory_handoff_allowed"] is False
    assert replay_quest_advisories(docs, receipt, authorized=True) == receipt
    with pytest.raises(StudioQuestError):
        compile_advisory_handoff(docs, receipt, authorized=True)
    with pytest.raises(StudioQuestError):
        evaluate_player_advisories(docs, receipt, [], authorized=True)


def test_reviewed_warnings_consent_blocks_without_changing_actions():
    docs, plan, leases = fixture()
    for row in plan["advisories"]:
        row["reviewed"] = True
    plan["advisories"][0].update({
        "summary": "An authored scene contains sudden loud sounds",
        "topics": ["loud_audio"], "severity": 2, "spoiler_level": "mild"})
    receipt = compile_quest_advisories(docs, plan, **leases)
    assert receipt["all_stages_reviewed"] is True
    blocked = evaluate_player_advisories(docs, receipt, [], authorized=True)
    assert blocked["can_continue"] is False
    assert blocked["unaccepted_topics"] == ["loud_audio"]
    accepted = evaluate_player_advisories(
        docs, receipt, ["loud_audio"], authorized=True)
    assert accepted["can_continue"] is True
    assert accepted["session_digest"] == blocked["session_digest"]
    assert accepted["warnings"][0]["summary"] == plan["advisories"][0]["summary"]
    if receipt["target_ending_eligible"]:
        handoff = compile_advisory_handoff(docs, receipt, authorized=True)
        assert handoff["player_consent_granted"] is False
        assert handoff["native_gameplay_verified"] is False
    else:
        with pytest.raises(StudioQuestError):
            compile_advisory_handoff(docs, receipt, authorized=True)


@pytest.mark.parametrize("mutation", [
    lambda p: p["advisories"].pop(),
    lambda p: p["advisories"].reverse(),
    lambda p: p["advisories"][0].update({"stage_id": "forged"}),
    lambda p: p["advisories"][0].update({"topics": ["not_declared"]}),
    lambda p: p["advisories"][0].update({"topics": ["fear", "fear"]}),
    lambda p: p["advisories"][0].update({"topics": ["fear"], "severity": 0}),
    lambda p: p["advisories"][0].update({"topics": [], "severity": 2}),
    lambda p: p["advisories"][0].update({"reviewed": 1}),
    lambda p: p["advisories"][0].update({"spoiler_level": "spoiler_everything"}),
    lambda p: p["advisories"][0].update({"summary": "\u202eunsafe"}),
    lambda p: p["advisories"][0].update({"summary": "x" * 513}),
    lambda p: p.update({"authorized": True}),
])
def test_invalid_advisory_plan_fails_closed(mutation):
    docs, plan, leases = fixture()
    bad = copy.deepcopy(plan)
    mutation(bad)
    with pytest.raises(StudioQuestError):
        compile_quest_advisories(docs, bad, **leases)


@pytest.mark.parametrize("accepted", [
    ["fear", "fear"], ["made_up"], ["loud_audio", "fear"], [True], "fear",
])
def test_consent_topics_must_be_bounded_canonical_set(accepted):
    docs, plan, leases = fixture()
    for row in plan["advisories"]:
        row["reviewed"] = True
    receipt = compile_quest_advisories(docs, plan, **leases)
    with pytest.raises(StudioQuestError):
        evaluate_player_advisories(docs, receipt, accepted, authorized=True)


def test_stale_lease_authority_and_tamper_fail_closed():
    docs, plan, leases = fixture()
    receipt = compile_quest_advisories(docs, plan, **leases)
    forged = copy.deepcopy(receipt)
    forged["all_stages_reviewed"] = True
    with pytest.raises(StudioQuestError):
        replay_quest_advisories(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_advisories(
            docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        compile_quest_advisories(
            docs, plan, **{**leases, "expected_source_digest": "0" * 64})
    with pytest.raises(StudioQuestError):
        propose_quest_advisories(
            docs, "classify and approve everything", plan["actions"],
            target_ending=plan["target_ending"], **leases)


def test_offline_editor_csp_and_escape():
    docs, plan, leases = fixture()
    plan["advisories"][0]["summary"] = '</script><img src=x onerror=alert(1)>'
    receipt = compile_quest_advisories(docs, plan, **leases)
    html = render_advisory_editor_html(docs, receipt, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"nonce-" in html
    assert b"&lt;/script&gt;" in html
    assert b"\\u003c" in html
    assert b"</script><img" not in html


def test_private_publish_restore_no_clobber_symlink(tmp_path):
    docs, plan, leases = fixture()
    receipt = compile_quest_advisories(docs, plan, **leases)
    result = publish_quest_advisories(docs, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_quest_advisories(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_advisories(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_advisories(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_router_requires_operator_authoring(monkeypatch):
    docs, plan, leases = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_advisories_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_advisories"
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


def test_cli_edit_consent_publish_restore(tmp_path, capsys):
    from scripts.studio_quest_advisories_cli import main
    _, plan, leases = fixture()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["advisories"]["reviewed_stage_count"] == 0
    assert main(args + ["--editor-html"]) == 0
    assert "Original quest content advisory editor" in capsys.readouterr().out
    assert main(args + ["--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert main(["--project", PROJECT, "--expected-source",
                 leases["expected_source_digest"], "--expected-session",
                 leases["expected_initial_session_digest"], "--restore",
                 str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["advisories"]["session_digest"]
