"""Canonical branch comparison, tamper and custody acceptance."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_branch_review import (
    FILENAME, PROMPT, propose_quest_branch_review,
    compile_quest_branch_review, replay_quest_branch_review,
    compile_quest_branch_handoff, publish_quest_branch_review,
    restore_quest_branch_review, render_quest_branch_editor_html,
)


def source():
    return {
        "quest": {"project_id": "branch_demo", "release_certified": False,
                  "stage_graph": [
                      {"id": "gate", "prerequisites": [], "alternatives": ["help", "ignore"],
                       "reward": "gate_pass", "choice_effects": {
                           "help": ["choice:gate:kind"], "ignore": ["choice:gate:cold"]}},
                      {"id": "harbor", "prerequisites": ["gate"],
                       "alternatives": ["sail", "stay"], "reward": "harbor_pass"}]},
        "narrative": {"project_id": "branch_demo", "release_certified": False,
                      "endings": [
                          {"id": "rescue", "requires": ["choice:gate:kind", "harbor_pass"]},
                          {"id": "exile", "requires": ["choice:gate:cold", "harbor_pass"]}]},
    }


def make_plan(docs=None):
    docs = docs or source()
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    plan = propose_quest_branch_review(
        docs, PROMPT, [["gate", "help"], ["harbor", "sail"]],
        [["gate", "ignore"], ["harbor", "stay"]], "rescue", authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    return docs, program, initial, plan


def compile_plan(docs, program, initial, plan):
    return compile_quest_branch_review(
        docs, plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)


def test_endings_are_replayed_not_inferred_from_review():
    docs, program, initial, plan = make_plan()
    receipt = compile_plan(docs, program, initial, plan)
    assert receipt["left_only_endings"] == ["rescue"]
    assert receipt["right_only_endings"] == ["exile"]
    assert receipt["common_prefix_actions"] == 0
    assert receipt["selected_target_eligible"] is True
    assert receipt["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_branch_handoff(docs, receipt, authorized=True)
    plan["reviewed"] = True
    plan["review_note"] = "Reviewed original choice consequences"
    checked = compile_plan(docs, program, initial, plan)
    handoff = compile_quest_branch_handoff(docs, checked, authorized=True)
    assert handoff["canonical_choices"] == [["gate", "help"], ["harbor", "sail"]]
    assert handoff["session_digest"] == checked["selected_session_digest"]
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False


def test_ineligible_selected_branch_is_fail_closed():
    docs, program, initial, plan = make_plan()
    plan["selected"] = "right"
    plan["reviewed"] = True
    receipt = compile_plan(docs, program, initial, plan)
    assert receipt["selected_target_eligible"] is False
    assert receipt["right_unmet_target_predicates"] == ["choice:gate:kind"]
    with pytest.raises(StudioQuestError):
        compile_quest_branch_handoff(docs, receipt, authorized=True)


def test_tampered_receipts_and_stale_source_fail():
    docs, program, initial, plan = make_plan()
    plan["reviewed"] = True
    receipt = compile_plan(docs, program, initial, plan)
    forged = copy.deepcopy(receipt)
    forged["left_only_endings"] = ["exile"]
    forged["branch_review_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        replay_quest_branch_review(docs, forged, authorized=True)
    stale = copy.deepcopy(docs)
    stale["quest"]["stage_graph"][0]["reward"] = "different"
    with pytest.raises(StudioQuestError):
        replay_quest_branch_review(stale, receipt, authorized=True)
    with pytest.raises(PermissionError):
        replay_quest_branch_review(docs, receipt, authorized=False)
    with pytest.raises(PermissionError):
        propose_quest_branch_review(
            docs, PROMPT, [], [], "rescue", authorized=False,
            expected_source_digest=program.source_digest,
            expected_initial_session_digest=initial.digest)


@pytest.mark.parametrize("field,value", [
    ("selected", "neither"), ("reviewed", 1), ("review_note", "bad\nline"),
    ("left_actions", [["harbor", "stay"]]), ("right_actions", [["gate", "fake"]]),
    ("target_ending", "fabricated"), ("review_note", "x" * 1025),
])
def test_invalid_edits_rejected(field, value):
    docs, program, initial, plan = make_plan()
    plan[field] = value
    with pytest.raises((StudioQuestError, ValueError)):
        compile_plan(docs, program, initial, plan)


def test_private_publish_restore_and_symlink(tmp_path):
    docs, program, initial, plan = make_plan()
    plan["reviewed"] = True
    receipt = compile_plan(docs, program, initial, plan)
    result = publish_quest_branch_review(docs, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_quest_branch_review(
        docs, tmp_path, authorized=True,
        expected_source_digest=program.source_digest) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_branch_review(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_branch_review(
            docs, tmp_path, authorized=True,
            expected_source_digest=program.source_digest)


def test_editor_csp_escapes_and_exports_typed_plan():
    docs, program, initial, plan = make_plan()
    plan["review_note"] = "</script><img src=x>"
    receipt = compile_plan(docs, program, initial, plan)
    html = render_quest_branch_editor_html(
        docs, receipt, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"form-action 'none'" in html
    assert b"\\u003c/script>" in html
    assert b"</script><img" not in html
    assert b"Export reviewed plan" in html


def test_cli_compiles_plan_and_handoff(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_branch_review_cli as cli
    docs, program, initial, plan = make_plan()
    plan["reviewed"] = True
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    assert cli.main(["--project", "branch_demo", "--plan", str(path),
                     "--handoff"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["playable_handoff"]["target_ending"] == "rescue"
    assert cli.main(["--project", "branch_demo", "--plan", str(path),
                     "--editor-html"]) == 0
    assert "Canonical quest branch comparison" in capsys.readouterr().out
