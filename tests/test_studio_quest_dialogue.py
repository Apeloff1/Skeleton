"""Original NPC dialogue requires reviewed authored text and canonical replay."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_dialogue import (
    FILENAME, PROMPT, propose_quest_dialogue, compile_quest_dialogue,
    replay_quest_dialogue, compile_quest_dialogue_handoff,
    publish_quest_dialogue, restore_quest_dialogue,
    render_quest_dialogue_editor_html,
)
from tests.test_studio_quest_npc_relationships import fixture, compile_plan


def make_dialogue():
    docs, program, initial, npc_plan = fixture()
    npc = compile_plan(docs, program, initial, npc_plan)
    plan = propose_quest_dialogue(
        docs, npc, PROMPT, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    return docs, program, initial, npc, plan


def compile_plan_dialogue(docs, program, initial, npc, plan):
    return compile_quest_dialogue(
        docs, npc, plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)


def review(plan):
    for i, row in enumerate(plan["lines"]):
        row["speaker"] = "captain" if i == 0 else "healer"
        row["text"] = "An original line " + str(i)
        row["reviewed"] = True
    return plan


def test_draft_requires_review_and_eligible_npc_route():
    docs, program, initial, npc, plan = make_dialogue()
    draft = compile_plan_dialogue(docs, program, initial, npc, plan)
    assert draft["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_dialogue_handoff(docs, npc, draft, authorized=True)
    receipt = compile_plan_dialogue(docs, program, initial, npc, review(plan))
    assert receipt["all_lines_reviewed"] is True
    assert receipt["reviewed_line_count"] == 2
    handoff = compile_quest_dialogue_handoff(
        docs, npc, receipt, authorized=True)
    assert handoff["canonical_choices"] == [["gate", "help"], ["harbor", "sail"]]
    assert handoff["authored_dialogue_lines"][0]["speaker"] == "captain"
    assert handoff["voice_audio_generated"] is False
    assert handoff["release_certified"] is False


def test_multiple_ordered_dialogue_beats_are_preserved():
    docs, program, initial, npc, plan = make_dialogue()
    plan = review(plan)
    extra = copy.deepcopy(plan["lines"][0])
    extra["beat_index"] = 1
    extra["text"] = "A second original sentence"
    plan["lines"].insert(1, extra)
    receipt = compile_plan_dialogue(docs, program, initial, npc, plan)
    assert receipt["line_count"] == 3
    assert receipt["playable_handoff_allowed"] is True


@pytest.mark.parametrize("field,value", [
    ("speaker", "forged_npc"), ("text", "bad\nline"),
    ("text", ""), ("delivery", "unsafe"), ("reviewed", 1),
    ("beat_index", 1), ("stage_id", "unknown"),
    ("choice", "unplayed"),
])
def test_invalid_reviewed_dialogue_rejected(field, value):
    docs, program, initial, npc, plan = make_dialogue()
    plan = review(plan)
    plan["lines"][0][field] = value
    with pytest.raises((StudioQuestError, ValueError)):
        compile_plan_dialogue(docs, program, initial, npc, plan)


def test_skipped_or_reordered_action_dialogue_fails():
    docs, program, initial, npc, plan = make_dialogue()
    plan = review(plan)
    plan["lines"].pop()
    with pytest.raises(StudioQuestError):
        compile_plan_dialogue(docs, program, initial, npc, plan)
    plan = review(make_dialogue()[4])
    plan["lines"].reverse()
    with pytest.raises(StudioQuestError):
        compile_plan_dialogue(docs, program, initial, npc, plan)


def test_forged_receipt_and_npc_lease_fail_closed():
    docs, program, initial, npc, plan = make_dialogue()
    receipt = compile_plan_dialogue(docs, program, initial, npc, review(plan))
    forged = copy.deepcopy(receipt)
    forged["authoring"]["lines"][0]["text"] = "Forged words"
    with pytest.raises(StudioQuestError):
        replay_quest_dialogue(docs, npc, forged, authorized=True)
    changed_npc = copy.deepcopy(npc)
    changed_npc["final_trust"][0]["trust"] = 99
    with pytest.raises(StudioQuestError):
        replay_quest_dialogue(docs, changed_npc, receipt, authorized=True)
    with pytest.raises(PermissionError):
        replay_quest_dialogue(docs, npc, receipt, authorized=False)


def test_private_publication_restore_and_symlink(tmp_path):
    docs, program, initial, npc, plan = make_dialogue()
    receipt = compile_plan_dialogue(docs, program, initial, npc, review(plan))
    result = publish_quest_dialogue(
        docs, npc, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_quest_dialogue(
        docs, npc, tmp_path, authorized=True,
        expected_source_digest=program.source_digest) == receipt
    with pytest.raises(FileExistsError):
        publish_quest_dialogue(docs, npc, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_dialogue(
            docs, npc, tmp_path, authorized=True,
            expected_source_digest=program.source_digest)


def test_editor_csp_and_cli_handoff(tmp_path, capsys, monkeypatch):
    from scripts import studio_quest_dialogue_cli as cli
    docs, program, initial, npc, plan = make_dialogue()
    plan = review(plan)
    plan["lines"][0]["text"] = "</script><img src=x>"
    receipt = compile_plan_dialogue(docs, program, initial, npc, plan)
    html = render_quest_dialogue_editor_html(
        docs, npc, receipt, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"\\u003c/script>" in html
    assert b"</script><img" not in html
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    npc_path = tmp_path / "npc.json"
    npc_path.write_text(json.dumps(npc))
    os.chmod(npc_path, 0o600)
    plan_path = tmp_path / "dialogue.json"
    plan_path.write_text(json.dumps(plan))
    os.chmod(plan_path, 0o600)
    assert cli.main(["--project", "branch_demo", "--npc-file", str(npc_path),
                     "--plan", str(plan_path), "--handoff"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["playable_handoff"]["authored_dialogue_lines"][0]["speaker"] == "captain"
