"""Canonical quest achievement source, replay, tamper, UI, CLI, custody."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest, step_quest,
)
from skeleton.ai.game_builder.studio_quest_achievements import (
    PROMPT, FILENAME, propose_quest_achievements,
    compile_quest_achievements, replay_quest_achievements,
    compile_achievement_handoff, publish_quest_achievements,
    restore_quest_achievements, render_achievement_editor_html,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.agents.jeeves.studio_quest_achievements_tool import REQUEST_SCHEMA

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    first = program.stages[0]
    session = step_quest(initial, docs, stage=first.key,
                         alternative=first.alternatives[0], authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_quest_achievements(
        docs, PROMPT, [[first.key, first.alternatives[0]]],
        target_ending=program.endings[0][0], **leases)
    return docs, plan, leases, session


def test_source_grounded_earned_milestone_and_playable_handoff():
    docs, plan, leases, session = fixture()
    receipt = compile_quest_achievements(docs, plan, **leases)
    assert receipt["session_digest"] == session.digest
    assert receipt["unlocked"][0]["id"] == "stage_1"
    assert receipt["sandbox_points"] == 10
    assert receipt["external_account_awards_verified"] is False
    assert receipt["release_certified"] is False
    assert replay_quest_achievements(docs, receipt, authorized=True) == receipt
    handoff = compile_achievement_handoff(docs, receipt, authorized=True)
    assert handoff["canonical_quest_replay_verified"] is True
    assert handoff["unlocked"] == receipt["unlocked"]
    assert handoff["native_gameplay_verified"] is False


def test_choice_and_effect_gated_achievement_never_forges_rewards():
    docs, plan, leases, _ = fixture()
    stage = compile_quest_program(docs).stages[0]
    row = plan["achievements"][0]
    row["required_choice"] = stage.alternatives[0]
    effect = dict(stage.choice_effects).get(stage.alternatives[0], ())
    if effect:
        row["required_effect"] = effect[0]
    earned = compile_quest_achievements(docs, plan, **leases)
    assert earned["unlocked"][0]["id"] == row["id"]
    if len(stage.alternatives) > 1:
        row["required_choice"] = stage.alternatives[1]
        row["required_effect"] = ""
        not_earned = compile_quest_achievements(docs, plan, **leases)
        assert row["id"] in not_earned["locked_ids"]


@pytest.mark.parametrize("mutation", [
    lambda p: p["achievements"].append(copy.deepcopy(p["achievements"][0])),
    lambda p: p["achievements"][0].update({"stage_id": "never-authored"}),
    lambda p: p["achievements"][0].update({"required_choice": "forged"}),
    lambda p: p["achievements"][0].update({"required_effect": "choice:fake"}),
    lambda p: p["achievements"][0].update({"points": True}),
    lambda p: p["achievements"][0].update({"points": 101}),
    lambda p: p["achievements"][0].update({"title": "\u202eunsafe"}),
    lambda p: p["achievements"][0].update({"id": "../unsafe"}),
    lambda p: p.update({"authorized": True}),
])
def test_forged_achievement_definition_fails_closed(mutation):
    docs, plan, leases, _ = fixture()
    bad = copy.deepcopy(plan)
    mutation(bad)
    with pytest.raises(StudioQuestError):
        compile_quest_achievements(docs, bad, **leases)


def test_stale_source_and_forged_unlock_receipt_fail_closed():
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_achievements(docs, plan, **leases)
    forged = copy.deepcopy(receipt)
    forged["sandbox_points"] += 1000
    with pytest.raises(StudioQuestError):
        replay_quest_achievements(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_achievements(docs, plan, **{**leases, "authorized": False})
    with pytest.raises(StudioQuestError):
        compile_quest_achievements(
            docs, plan, **{**leases, "expected_source_digest": "0" * 64})
    with pytest.raises(StudioQuestError):
        propose_quest_achievements(
            docs, "award real platform points", plan["actions"],
            target_ending=plan["target_ending"], **leases)


def test_html_escapes_untrusted_titles_and_disables_network():
    docs, plan, leases, _ = fixture()
    plan["achievements"][0]["title"] = '</script><img src=x onerror=alert(1)>'
    receipt = compile_quest_achievements(docs, plan, **leases)
    html = render_achievement_editor_html(docs, receipt, authorized=True)
    assert b"script-src 'sha256-" in html
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"&lt;/script&gt;" in html
    assert b"\\u003c" in html
    assert b"</script><img" not in html


def test_private_publication_restore_exclusive_link_and_symlink(tmp_path):
    docs, plan, leases, _ = fixture()
    receipt = compile_quest_achievements(docs, plan, **leases)
    assert publish_quest_achievements(
        docs, receipt, tmp_path, authorized=True)["file_write_performed"] is True
    assert restore_quest_achievements(
        docs, tmp_path, authorized=True,
        expected_source_digest=leases["expected_source_digest"]) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_achievements(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_achievements(
            docs, tmp_path, authorized=True,
            expected_source_digest=leases["expected_source_digest"])


def test_jeeves_router_requires_out_of_band_authoring(monkeypatch):
    docs, plan, leases, _ = fixture()
    from skeleton.ai.agents.jeeves import studio_quest_achievements_tool as adapter
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    name = "studio_original_quest_achievements"
    entry = next(row for row in world_tool_catalog()["tools"] if row["name"] == name)
    assert entry["explicit_authoring_permission_required"] is True
    request = {"tool": name, "arguments": {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "actions": plan["actions"], "target_ending": plan["target_ending"],
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"]}}
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    routed = route_world_tool(request, authorized=True, allow_authoring=True)
    assert routed["result"]["detail"] == plan
    assert routed["file_write_performed"] is False


def test_cli_edit_publish_restore_and_handoff(tmp_path, capsys):
    from scripts.studio_quest_achievements_cli import main
    docs, plan, leases, _ = fixture()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    args = ["--project", PROJECT, "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"], "--plan-file", str(path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["achievements"]["sandbox_points"] == 10
    assert main(args + ["--editor-html"]) == 0
    assert "Original quest achievement editor" in capsys.readouterr().out
    assert main(args + ["--handoff"]) == 0
    assert json.loads(capsys.readouterr().out)["playable_handoff"]["unlocked"]
    assert main(args + ["--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert main(["--project", PROJECT, "--expected-source",
                 leases["expected_source_digest"], "--expected-session",
                 leases["expected_initial_session_digest"], "--restore",
                 str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["achievements"]["sandbox_points"] == 10
