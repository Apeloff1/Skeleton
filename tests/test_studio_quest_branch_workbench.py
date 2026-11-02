"""Source-verified quest forks: typed prompt, approval, replay, custody and CLI."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_branch_workbench import (
    SCHEMA, APPROVAL_SCHEMA, PROMPT, compile_branch_workbench,
    propose_branch_workbench, replay_branch_workbench, approve_branch_fork,
    replay_approved_branch, compile_branch_handoff, publish_branch_checkpoint,
    restore_branch_checkpoint, render_branch_workbench_html, FILENAME,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_branch_workbench_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    session = start_quest(docs, authorized=True)
    plan = {"actions": [], "target_ending": program.endings[0][0]}
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": session.digest}
    return docs, plan, leases


def approval(proposal, index=0):
    return {"schema": APPROVAL_SCHEMA,
            "proposal_digest": proposal["proposal_digest"],
            "candidate_digest": proposal["candidates"][index]["candidate_digest"]}


def test_replay_legal_fork_requires_operator_approval():
    docs, plan, leases = fixture()
    proposed = compile_branch_workbench(docs, plan, **leases)
    assert proposed["schema"] == SCHEMA
    assert proposed["candidate_count"] >= 1
    assert proposed["playable_handoff_allowed"] is False
    assert proposed["file_write_performed"] is False
    assert replay_branch_workbench(docs, proposed, authorized=True) == proposed
    assert propose_branch_workbench(docs, PROMPT, plan, **leases) == proposed
    committed = approve_branch_fork(docs, proposed, approval(proposed), **leases)
    assert committed["actions"] == [proposed["candidates"][0]["action"]]
    assert committed["fork_session_digest"] == proposed["candidates"][0]["fork_session_digest"]
    assert replay_approved_branch(docs, committed, authorized=True) == committed
    assert committed["native_gameplay_verified"] is False
    assert committed["release_certified"] is False
    if committed["playable_handoff_allowed"]:
        handoff = compile_branch_handoff(docs, committed, authorized=True)
        assert handoff["quest_session_digest"] == committed["fork_session_digest"]
        assert handoff["release_certified"] is False
    else:
        with pytest.raises(StudioQuestError):
            compile_branch_handoff(docs, committed, authorized=True)


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"schema": "forged"}),
    lambda x: x.update({"candidate_digest": "0" * 64}),
    lambda x: x.update({"proposal_digest": "0" * 64}),
    lambda x: x.update({"authorized": True}),
    lambda x: x.pop("candidate_digest"),
])
def test_invalid_approvals_fail_closed(mutate):
    docs, plan, leases = fixture()
    proposed = compile_branch_workbench(docs, plan, **leases)
    bad = approval(proposed)
    mutate(bad)
    with pytest.raises(StudioQuestError):
        approve_branch_fork(docs, proposed, bad, **leases)


def test_stale_source_forged_proposal_checkpoint_and_prompt():
    docs, plan, leases = fixture()
    proposed = compile_branch_workbench(docs, plan, **leases)
    committed = approve_branch_fork(docs, proposed, approval(proposed), **leases)
    with pytest.raises(PermissionError):
        compile_branch_workbench(docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        propose_branch_workbench(docs, "automatically choose a branch", plan, **leases)
    forged = copy.deepcopy(proposed)
    forged["candidates"][0]["target_ending_eligible"] = True
    with pytest.raises(StudioQuestError):
        replay_branch_workbench(docs, forged, authorized=True)
    forged = copy.deepcopy(committed)
    forged["playable_handoff_allowed"] = True
    with pytest.raises(StudioQuestError):
        replay_approved_branch(docs, forged, authorized=True)
    changed = copy.deepcopy(docs)
    key = "stage_graph" if changed["quest"].get("stage_graph") else "stages"
    changed["quest"][key][0]["reward"] = "changed reward"
    with pytest.raises(StudioQuestError):
        replay_approved_branch(changed, committed, authorized=True)
    with pytest.raises(StudioQuestError):
        approve_branch_fork(docs, proposed, approval(proposed),
                            **{**leases, "expected_source_digest": "0" * 64})


def test_bounded_inputs_duplicate_and_illegal_actions():
    docs, plan, leases = fixture()
    for bad in [
        {"actions": [], "target_ending": plan["target_ending"], "authorized": True},
        {"actions": [["nonexistent", "choice"]], "target_ending": plan["target_ending"]},
        {"actions": [[]], "target_ending": plan["target_ending"]},
        {"actions": [], "target_ending": "unknown-ending"},
        {"actions": [["x", "y"]] * 65, "target_ending": plan["target_ending"]},
    ]:
        with pytest.raises(StudioQuestError):
            compile_branch_workbench(docs, bad, **leases)


def test_offline_html_csp_and_escaped_text():
    docs, plan, leases = fixture()
    proposed = compile_branch_workbench(docs, plan, **leases)
    html = render_branch_workbench_html(docs, proposed, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"Export selected fork" in html
    assert proposed["proposal_digest"].encode("ascii") in html


def test_private_publication_restore_and_no_overwrite(tmp_path):
    docs, plan, leases = fixture()
    proposed = compile_branch_workbench(docs, plan, **leases)
    committed = approve_branch_fork(docs, proposed, approval(proposed), **leases)
    published = publish_branch_checkpoint(docs, committed, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert (tmp_path / FILENAME).exists()
    assert restore_branch_checkpoint(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == committed
    with pytest.raises(FileExistsError):
        publish_branch_checkpoint(docs, committed, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_branch_checkpoint(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_jeeves_route_requires_explicit_authoring_permission(monkeypatch):
    docs, plan, leases = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_branch_workbench_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_branch_workbench"
    entry = next(x for x in world_tool_catalog()["tools"] if x["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT, "authoring": plan,
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"]}}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    routed = route_world_tool(request, authorized=True, allow_authoring=True)
    assert routed["result"]["detail"]["candidate_count"] >= 1
    assert routed["file_write_performed"] is False


def test_cli_preview_approval_private_restore_and_no_silent_save(tmp_path, capsys):
    from scripts.studio_quest_branch_workbench_cli import main
    docs, plan, leases = fixture()
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))
    os.chmod(plan_file, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(plan_file)]
    assert main(args) == 0
    proposed = json.loads(capsys.readouterr().out)["proposal"]
    assert main(args + ["--review-html"]) == 0
    assert "Quest branch workbench" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(args + ["--publish", str(tmp_path)])
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(json.dumps(approval(proposed)))
    os.chmod(approval_file, 0o600)
    assert main(args + ["--approve", "--approval-file", str(approval_file),
                        "--publish", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["file_write_performed"] is True
    assert result["checkpoint"]["canonical_quest_replay_verified"] is True
    assert main(["--project", PROJECT, "--expected-source",
                 leases["expected_source_digest"], "--expected-session",
                 leases["expected_initial_session_digest"], "--restore",
                 str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["checkpoint"] == result["checkpoint"]
