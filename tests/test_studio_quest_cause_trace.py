"""Quest causal provenance: end-to-end prompt, source replay, custody and handoff."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest,
    start_quest,
)
from skeleton.ai.game_builder.studio_quest_cause_trace import (
    PROMPT, FILENAME, propose_quest_cause_trace, compile_quest_cause_trace,
    replay_quest_cause_trace, compile_quest_cause_handoff,
    publish_quest_cause_trace, restore_quest_cause_trace,
    render_quest_cause_html,
)
from tests.test_studio_quest_character_locale import fixture


def prepared():
    documents = fixture()[0]
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    plan = propose_quest_cause_trace(
        documents, PROMPT, actions, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    return documents, program, initial, plan


def compile_checked(documents, program, initial, plan):
    return compile_quest_cause_trace(
        documents, plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)


def test_prompt_review_canonical_provenance_and_replay():
    documents, program, initial, plan = prepared()
    assert plan["reviewed"] is False
    with pytest.raises(StudioQuestError, match="unreviewed"):
        compile_checked(documents, program, initial, plan)
    plan["reviewed"] = True
    trace = compile_checked(documents, program, initial, plan)
    final = replay_quest(documents, plan["actions"], authorized=True)
    progress = quest_progress(final, documents)
    assert trace["final_session_digest"] == final.digest
    assert trace["canonical_quest_replay_verified"] is True
    assert trace["authored_predicate_provenance_verified"] is True
    assert trace["native_gameplay_verified"] is False
    assert trace["release_certified"] is False
    assert replay_quest_cause_trace(documents, trace, authorized=True) == trace
    assert len(trace["frames"]) == len(final.choices)
    for index, frame in enumerate(trace["frames"]):
        assert frame["action_index"] == index
        assert frame["stage_id"] == final.choices[index][0]
        assert frame["session_digest"] != frame["previous_session_digest"]
    for ending in trace["ending_explanations"]:
        assert ending["eligible"] == (
            ending["ending_id"] in progress["sandbox_endings_eligible"])
        assert ending["missing_predicates"] == [
            row["predicate"] for row in ending["predicates"] if not row["earned"]]
        for cause in ending["predicates"]:
            if cause["earned"]:
                origin = cause["origin"]
                assert type(origin["action_index"]) is int
                assert origin["stage_id"] == final.choices[origin["action_index"]][0]
                assert cause["predicate"] in trace["frames"][
                    origin["action_index"]]["earned_tokens"]
            else:
                assert cause["origin"] is None
    html = render_quest_cause_html(documents, trace, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"native gameplay proof" in html
    assert b"<script" not in html


def test_handoff_requires_every_selected_ending_earned():
    documents, program, initial, plan = prepared()
    plan["reviewed"] = True
    trace = compile_checked(documents, program, initial, plan)
    earned = [row["ending_id"] for row in trace["ending_explanations"]
              if row["eligible"]]
    missing = [row["ending_id"] for row in trace["ending_explanations"]
               if not row["eligible"]]
    if missing:
        with pytest.raises(StudioQuestError, match="unearned"):
            compile_quest_cause_handoff(documents, trace, authorized=True)
    if earned:
        subset = copy.deepcopy(plan)
        subset["target_endings"] = earned
        verified = compile_checked(documents, program, initial, subset)
        handoff = compile_quest_cause_handoff(
            documents, verified, authorized=True)
        assert handoff["eligible_endings"] == earned
        assert handoff["quest_source_digest"] == program.source_digest
        assert handoff["native_gameplay_verified"] is False
        assert handoff["release_certified"] is False


def test_plan_leases_authority_and_target_integrity():
    documents, program, initial, plan = prepared()
    plan["reviewed"] = True
    with pytest.raises(PermissionError):
        compile_quest_cause_trace(
            documents, plan, authorized=False,
            expected_source_digest=program.source_digest,
            expected_initial_session_digest=initial.digest)
    with pytest.raises(StudioQuestError):
        propose_quest_cause_trace(
            documents, "invent my reward", plan["actions"], authorized=True,
            expected_source_digest=program.source_digest,
            expected_initial_session_digest=initial.digest)
    for field, replacement in (
        ("source_digest", "0" * 64),
        ("initial_session_digest", "0" * 64),
        ("final_session_digest", "0" * 64),
        ("reviewed", 1),
        ("target_endings", []),
        ("target_endings", [plan["target_endings"][0]] * 2),
        ("target_endings", ["forged"]),
        ("actions", [["forged", "forged"]]),
    ):
        changed = copy.deepcopy(plan)
        changed[field] = replacement
        with pytest.raises((StudioQuestError, TypeError, ValueError)):
            compile_checked(documents, program, initial, changed)
    changed = copy.deepcopy(plan)
    changed["new_claim"] = "external proof"
    with pytest.raises(StudioQuestError):
        compile_checked(documents, program, initial, changed)
    altered = copy.deepcopy(documents)
    altered["quest"]["stage_graph"][0]["reward"] = "altered_reward"
    with pytest.raises(StudioQuestError):
        compile_checked(altered, program, initial, plan)


def test_forged_receipt_and_unearned_certification_rejected():
    documents, program, initial, plan = prepared()
    plan["reviewed"] = True
    trace = compile_checked(documents, program, initial, plan)
    for path, value in (
        (("release_certified",), True),
        (("trace_digest",), "0" * 64),
        (("frames", 0, "earned_tokens"), ["invented_fact"]),
        (("ending_explanations", 0, "eligible"), True),
    ):
        altered = copy.deepcopy(trace)
        ref = altered
        for key in path[:-1]:
            ref = ref[key]
        ref[path[-1]] = value
        if altered == trace:
            continue
        with pytest.raises(StudioQuestError):
            replay_quest_cause_trace(documents, altered, authorized=True)
    with pytest.raises(PermissionError):
        replay_quest_cause_trace(documents, trace, authorized=False)


def test_private_publication_restore_symlink_and_no_overwrite(tmp_path):
    documents, program, initial, plan = prepared()
    plan["reviewed"] = True
    trace = compile_checked(documents, program, initial, plan)
    published = publish_quest_cause_trace(
        documents, trace, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert restore_quest_cause_trace(
        documents, tmp_path, authorized=True,
        expected_source_digest=program.source_digest) == trace
    with pytest.raises(FileExistsError):
        publish_quest_cause_trace(documents, trace, tmp_path, authorized=True)
    file = tmp_path / FILENAME
    file.unlink()
    file.symlink_to(tmp_path / "missing")
    with pytest.raises((OSError, StudioQuestError)):
        restore_quest_cause_trace(
            documents, tmp_path, authorized=True,
            expected_source_digest=program.source_digest)
    file.unlink()
    file.write_text('{"schema":"a","schema":"b"}')
    os.chmod(file, 0o600)
    with pytest.raises(StudioQuestError):
        restore_quest_cause_trace(
            documents, tmp_path, authorized=True,
            expected_source_digest=program.source_digest)


def test_cli_proposal_review_persist_restore_and_html(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_cause_trace_cli as cli
    documents, program, initial, plan = prepared()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: documents)
    actions_file = tmp_path / "actions.json"
    actions_file.write_text(json.dumps({"actions": plan["actions"]}))
    os.chmod(actions_file, 0o600)
    args = ["--project", program.project_id]
    assert cli.main(args + ["--actions-file", str(actions_file)]) == 0
    proposed = json.loads(capsys.readouterr().out)["plan"]
    assert proposed["reviewed"] is False
    proposed["reviewed"] = True
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(proposed))
    os.chmod(plan_file, 0o600)
    assert cli.main(args + ["--plan-file", str(plan_file),
                            "--publish", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["file_write_performed"] is True
    assert cli.main(args + ["--restore", str(tmp_path)]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["trace"]["trace_digest"] == result["trace"]["trace_digest"]
    assert cli.main(args + ["--restore", str(tmp_path), "--html"]) == 0
    assert "Authored quest cause trace" in capsys.readouterr().out
