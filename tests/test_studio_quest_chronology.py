"""Canonical quest chronology time-window, replay and custody tests."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_chronology import (
    PROMPT, FILENAME, propose_quest_chronology, compile_quest_chronology,
    replay_quest_chronology, publish_quest_chronology,
    restore_quest_chronology, render_quest_chronology_editor,
    render_quest_chronology_preview,
)
from tests.test_studio_quest_character_locale import fixture


def prepared():
    documents = fixture()[0]
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    plan = propose_quest_chronology(
        documents, PROMPT, actions, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    for row in plan["rows"]:
        row["reviewed"] = True
        row["note"] = "Verified authored sequence."
    return documents, program, initial, plan


def compile_checked(documents, program, initial, plan):
    return compile_quest_chronology(
        documents, plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)


def test_prompt_to_reviewed_chronology_playable_handoff():
    documents, program, initial, plan = prepared()
    result = compile_checked(documents, program, initial, plan)
    assert result["source_digest"] == program.source_digest
    assert result["timeline"][0]["slack_minutes"] == 10
    assert result["canonical_quest_replay_verified"] is True
    assert result["temporal_window_consistency_verified"] is True
    assert result["external_clock_verified"] is False
    assert result["release_certified"] is False
    assert replay_quest_chronology(documents, result, authorized=True) == result
    assert b"Export edited chronology" in render_quest_chronology_editor(
        documents, plan, authorized=True)
    preview = render_quest_chronology_preview(
        documents, result, authorized=True)
    assert b"Content-Security-Policy" in preview
    assert b"not observed wall-clock" in preview


def test_overlap_deadline_and_temporal_inequality_rejected():
    documents, program, initial, plan = prepared()
    for field, value in (
        ("start_minute", -1), ("start_minute", True),
        ("duration_minutes", 0), ("duration_minutes", 1441),
        ("not_before_minute", 10081), ("deadline_minute", 0),
        ("deadline_minute", 10081), ("reviewed", 1),
    ):
        changed = copy.deepcopy(plan)
        changed["rows"][0][field] = value
        with pytest.raises(StudioQuestError):
            compile_checked(documents, program, initial, changed)
    changed = copy.deepcopy(plan)
    changed["rows"][0]["start_minute"] = 25
    with pytest.raises(StudioQuestError, match="impossible"):
        compile_checked(documents, program, initial, changed)
    if len(plan["rows"]) > 1:
        changed = copy.deepcopy(plan)
        changed["rows"][1]["start_minute"] = 10
        with pytest.raises(StudioQuestError, match="overlapping"):
            compile_checked(documents, program, initial, changed)


def test_identity_and_canonical_lease_rejection():
    documents, program, initial, plan = prepared()
    for field, value in (("stage_id", "forged"), ("choice", "forged")):
        changed = copy.deepcopy(plan)
        changed["rows"][0][field] = value
        with pytest.raises(StudioQuestError, match="identity"):
            compile_checked(documents, program, initial, changed)
    changed = copy.deepcopy(plan)
    changed["rows"][0]["reviewed"] = False
    with pytest.raises(StudioQuestError, match="reviewed"):
        compile_checked(documents, program, initial, changed)
    changed = copy.deepcopy(plan)
    changed["rows"][0]["note"] = "unsafe\u202e"
    with pytest.raises(StudioQuestError):
        compile_checked(documents, program, initial, changed)
    changed = copy.deepcopy(plan)
    changed["session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_checked(documents, program, initial, changed)
    forged = copy.deepcopy(documents)
    forged["quest"]["stage_graph"][0]["reward"] = "forged"
    with pytest.raises(StudioQuestError):
        compile_checked(forged, program, initial, plan)
    with pytest.raises(PermissionError):
        compile_quest_chronology(
            documents, plan, authorized=False,
            expected_source_digest=program.source_digest,
            expected_initial_session_digest=initial.digest)


def test_private_receipt_cannot_overwrite_or_replay_forgery(tmp_path):
    documents, program, initial, plan = prepared()
    checked = compile_checked(documents, program, initial, plan)
    published = publish_quest_chronology(
        documents, checked, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert restore_quest_chronology(documents, tmp_path, authorized=True) == checked
    with pytest.raises(FileExistsError):
        publish_quest_chronology(documents, checked, tmp_path, authorized=True)
    path = tmp_path / FILENAME
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises((OSError, StudioQuestError)):
        restore_quest_chronology(documents, tmp_path, authorized=True)
    path.unlink()
    path.write_text(json.dumps({**checked, "end_minute": 9999}))
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        restore_quest_chronology(documents, tmp_path, authorized=True)


def test_cli_proposal_review_publish_restore(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_chronology_cli as cli
    documents, program, initial, plan = prepared()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: documents)
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({"actions": plan["actions"]}))
    os.chmod(actions, 0o600)
    args = ["--project", "original_demo", "--actions-file", str(actions)]
    assert cli.main(args) == 0
    proposal = json.loads(capsys.readouterr().out)["plan"]
    assert proposal["rows"][0]["reviewed"] is False
    assert cli.main(args + ["--editor-html"]) == 0
    assert "Export edited chronology" in capsys.readouterr().out
    path = tmp_path / "reviewed.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    assert cli.main(args + ["--plan-file", str(path), "--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert cli.main(["--project", "original_demo", "--restore", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["chronology"]["release_certified"] is False
