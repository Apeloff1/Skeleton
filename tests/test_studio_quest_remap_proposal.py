"""End-to-end original quest remap proposal, operator approval and replay."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_quest_remap_proposal import (
    SCHEMA, EXPORT_SCHEMA, PROMPT, compile_quest_remap_proposal,
    replay_quest_remap_proposal, approve_quest_remap_proposal,
    propose_quest_remaps, render_quest_remap_review_html,
)
from skeleton.ai.agents.jeeves.studio_quest_remap_proposal_tool import REQUEST_SCHEMA
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.game_builder.studio_quest_revision_migration import (
    compile_quest_migration_handoff, replay_quest_revision_migration,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from tests.test_studio_quest_revision_migration import fixture, PROJECT


def make():
    docs, plan, leases, changed = fixture()
    authoring = {key: plan[key] for key in (
        "revision_request", "actions", "target_ending")}
    return docs, authoring, leases, changed


def approval(proposal, remaps=None):
    return {
        "schema": EXPORT_SCHEMA,
        "proposal_digest": proposal["proposal_digest"],
        "remaps": copy.deepcopy(
            proposal["candidate_remaps"] if remaps is None else remaps),
    }


def test_source_derived_candidate_requires_explicit_approval():
    docs, authoring, leases, changed = make()
    proposed = compile_quest_remap_proposal(docs, authoring, **leases)
    assert proposed["schema"] == SCHEMA
    assert proposed["status"] == "approval_required"
    assert proposed["requires_explicit_operator_approval"] is True
    assert proposed["playable_handoff_allowed"] is False
    assert proposed["candidate_count"] == 1
    assert proposed["candidate_remaps"][0]["to_choice"] == changed
    assert replay_quest_remap_proposal(docs, proposed, authorized=True) == proposed
    assert propose_quest_remaps(docs, PROMPT, authoring, **leases) == proposed
    migrated = approve_quest_remap_proposal(
        docs, proposed, approval(proposed), **leases)
    assert migrated["first_unmigrated_index"] is None
    assert migrated["migrated_actions"][0][1] == changed
    assert replay_quest_revision_migration(docs, migrated, authorized=True) == migrated
    if migrated["playable_handoff_allowed"]:
        handoff = compile_quest_migration_handoff(docs, migrated, authorized=True)
        assert handoff["native_gameplay_verified"] is False
        assert handoff["release_certified"] is False


@pytest.mark.parametrize("mutator", [
    lambda x: x.update({"proposal_digest": "0" * 64}),
    lambda x: x.update({"schema": "unknown"}),
    lambda x: x.update({"remaps": []}),
    lambda x: x["remaps"][0].update({"to_choice": "forged"}),
    lambda x: x["remaps"].append(copy.deepcopy(x["remaps"][0])),
    lambda x: x.update({"authorized": True}),
])
def test_approval_rejects_missing_forged_duplicate_or_embedded_authority(mutator):
    docs, authoring, leases, _ = make()
    proposed = compile_quest_remap_proposal(docs, authoring, **leases)
    bad = approval(proposed)
    mutator(bad)
    with pytest.raises(StudioQuestError):
        approve_quest_remap_proposal(docs, proposed, bad, **leases)


def test_stale_source_session_forged_receipt_and_prompt_fail_closed():
    docs, authoring, leases, _ = make()
    proposed = compile_quest_remap_proposal(docs, authoring, **leases)
    with pytest.raises(PermissionError):
        compile_quest_remap_proposal(
            docs, authoring, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        propose_quest_remaps(docs, "silently migrate every choice", authoring, **leases)
    forged = copy.deepcopy(proposed)
    forged["playable_handoff_allowed"] = True
    with pytest.raises(StudioQuestError):
        replay_quest_remap_proposal(docs, forged, authorized=True)
    with pytest.raises(StudioQuestError):
        approve_quest_remap_proposal(
            docs, proposed, approval(proposed),
            **{**leases, "expected_source_digest": "0" * 64})
    drift = copy.deepcopy(docs)
    source_key = "stage_graph" if drift["quest"].get("stage_graph") else "stages"
    drift["quest"][source_key][0]["reward"] = "forged reward"
    with pytest.raises(StudioQuestError):
        replay_quest_remap_proposal(drift, proposed, authorized=True)


def test_review_html_csp_no_network_and_escaped_authored_text():
    docs, authoring, leases, _ = make()
    proposed = compile_quest_remap_proposal(docs, authoring, **leases)
    html = render_quest_remap_review_html(docs, proposed, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"Export for explicit CLI approval" in html
    assert proposed["proposal_digest"].encode("ascii") in html
    assert b"release gates are still required" in html


def test_jeeves_route_read_only_preview_requires_authoring_opt_in(monkeypatch):
    docs, authoring, leases, _ = make()
    from skeleton.ai.agents.jeeves import studio_quest_remap_proposal_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda pid: docs)
    name = "studio_original_quest_remap_proposal"
    entry = next(x for x in world_tool_catalog()["tools"] if x["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT, "authoring": authoring,
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"],
    }}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    result = route_world_tool(request, authorized=True, allow_authoring=True)
    assert result["result"]["detail"]["candidate_count"] == 1
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False


def test_cli_proposal_review_and_private_approved_migration(tmp_path, capsys):
    from scripts.studio_quest_remap_proposal_cli import main
    docs, authoring, leases, _ = make()
    plan_path = tmp_path / "proposal.json"
    plan_path.write_text(json.dumps(authoring))
    os.chmod(plan_path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(plan_path)]
    assert main(args) == 0
    proposed = json.loads(capsys.readouterr().out)["proposal"]
    assert proposed["playable_handoff_allowed"] is False
    assert main(args + ["--review-html"]) == 0
    assert "Quest choice remap review" in capsys.readouterr().out
    approved_path = tmp_path / "approval.json"
    approved_path.write_text(json.dumps(approval(proposed)))
    os.chmod(approved_path, 0o600)
    assert main(args + ["--approve", "--approval-file", str(approved_path),
                        "--publish", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["file_write_performed"] is True
    assert payload["migration"]["first_unmigrated_index"] is None
    assert payload["release_certified"] is False


def test_cli_requires_explicit_approval_even_with_file(tmp_path):
    from scripts.studio_quest_remap_proposal_cli import main
    docs, authoring, leases, _ = make()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(authoring))
    os.chmod(path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(path)]
    with pytest.raises(SystemExit):
        main(args + ["--publish", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(args + ["--approval-file", str(path)])
