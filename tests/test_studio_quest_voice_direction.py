"""End-to-end original voice direction, source lease and custody regression."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_character_locale import (
    compile_quest_character_locale_handoff,
)
from skeleton.ai.game_builder.studio_quest_voice_direction import (
    PROMPT, FILENAME, propose_voice_direction, compile_voice_direction,
    replay_voice_direction, publish_voice_direction, restore_voice_direction,
    render_voice_direction_editor, render_voice_direction_preview,
)
from tests.test_studio_quest_character_locale import fixture


def prepared():
    parts = fixture()
    base = compile_quest_character_locale_handoff(*parts, authorized=True)
    plan = propose_voice_direction(
        parts[0], *parts[1:], prompt=PROMPT,
        expected_handoff_digest=base["handoff_digest"], authorized=True)
    for row in plan["rows"]:
        row["style"] = "gentle"
        row["rate"] = "measured"
        row["pause_after_ms"] = 250
        row["director_note"] = "Let the player consider the choice."
        row["reviewed"] = True
    return parts, base, plan


def compile_checked(parts, base, plan):
    return compile_voice_direction(
        parts[0], *parts[1:], plan=plan,
        expected_handoff_digest=base["handoff_digest"], authorized=True)


def test_prompt_to_reviewed_cue_to_replay_and_html():
    parts, base, plan = prepared()
    result = compile_checked(parts, base, plan)
    assert result["source_digest"] == base["source_digest"]
    assert result["session_digest"] == base["session_digest"]
    assert result["target_ending"] == base["target_ending"]
    assert result["cue_count"] == len(plan["rows"])
    assert result["audio_generated"] is False
    assert result["voice_identity_verified"] is False
    assert result["release_certified"] is False
    assert replay_voice_direction(
        parts[0], *parts[1:], receipt=result, authorized=True) == result
    html = render_voice_direction_editor(
        parts[0], *parts[1:], plan=plan, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"connect-src 'none'" in html
    assert b"Export reviewed plan" in html
    preview = render_voice_direction_preview(
        parts[0], *parts[1:], receipt=result, authorized=True)
    assert b"No audio synthesized" in preview


def test_reject_unreviewed_and_modified_canonical_identity():
    parts, base, plan = prepared()
    plan["rows"][0]["reviewed"] = False
    with pytest.raises(StudioQuestError, match="human review"):
        compile_checked(parts, base, plan)
    plan["rows"][0]["reviewed"] = True
    for field, forged in (("speaker", "impostor"), ("choice", "invented"),
                          ("display", "rewritten"), ("beat_index", 999)):
        changed = copy.deepcopy(plan)
        changed["rows"][0][field] = forged
        with pytest.raises(StudioQuestError, match="identity"):
            compile_checked(parts, base, changed)


def test_reject_bounds_control_chars_and_digest_forgery():
    parts, base, plan = prepared()
    for field, invalid in (("pause_after_ms", -1), ("pause_after_ms", 4001),
                           ("pause_after_ms", True), ("rate", "instant"),
                           ("style", "celebrity"), ("reviewed", 1)):
        forged = copy.deepcopy(plan)
        forged["rows"][0][field] = invalid
        with pytest.raises(StudioQuestError):
            compile_checked(parts, base, forged)
    forged = copy.deepcopy(plan)
    forged["rows"][0]["director_note"] = "<script>\u202e"
    with pytest.raises(StudioQuestError):
        compile_checked(parts, base, forged)
    forged = copy.deepcopy(plan)
    forged["handoff_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_checked(parts, base, forged)
    with pytest.raises(StudioQuestError):
        propose_voice_direction(parts[0], *parts[1:], prompt="fake",
                                expected_handoff_digest=base["handoff_digest"],
                                authorized=True)


def test_authority_and_source_change_fail_closed():
    parts, base, plan = prepared()
    with pytest.raises(PermissionError):
        compile_voice_direction(
            parts[0], *parts[1:], plan=plan,
            expected_handoff_digest=base["handoff_digest"], authorized=False)
    with pytest.raises(PermissionError):
        propose_voice_direction(
            parts[0], *parts[1:], prompt=PROMPT,
            expected_handoff_digest=base["handoff_digest"], authorized=False)
    forged = copy.deepcopy(parts)
    forged[0]["quest"]["stage_graph"][0]["reward"] = "forged"
    with pytest.raises(StudioQuestError):
        compile_checked(forged, base, plan)


def test_private_publication_restore_tamper_and_symlink(tmp_path):
    parts, base, plan = prepared()
    checked = compile_checked(parts, base, plan)
    published = publish_voice_direction(
        parts[0], *parts[1:], receipt=checked,
        directory=tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    assert restore_voice_direction(
        parts[0], *parts[1:], directory=tmp_path, authorized=True) == checked
    with pytest.raises(FileExistsError):
        publish_voice_direction(parts[0], *parts[1:], receipt=checked,
                                directory=tmp_path, authorized=True)
    target = tmp_path / FILENAME
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises((OSError, StudioQuestError)):
        restore_voice_direction(
            parts[0], *parts[1:], directory=tmp_path, authorized=True)
    target.unlink()
    target.write_text(json.dumps({**checked, "cue_count": 99}))
    os.chmod(target, 0o600)
    with pytest.raises(StudioQuestError):
        restore_voice_direction(
            parts[0], *parts[1:], directory=tmp_path, authorized=True)


def test_cli_proposal_editor_compile_and_publish(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_voice_direction_cli as cli
    parts, base, plan = prepared()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: parts[0])
    fields = ("branch", "npc", "dialogue", "dialogue-locale",
              "localization", "achievements", "pacing", "advisories")
    args = ["--project", "original_demo"]
    for field, value in zip(fields, parts[1:-1]):
        path = tmp_path / (field + ".json")
        path.write_text(json.dumps(value))
        os.chmod(path, 0o600)
        args += ["--" + field + "-file", str(path)]
    args += ["--accept-topic", "loud_audio"]
    assert cli.main(args) == 0
    proposal = json.loads(capsys.readouterr().out)["plan"]
    assert proposal["rows"][0]["reviewed"] is False
    assert cli.main(args + ["--editor-html"]) == 0
    assert "Export reviewed plan" in capsys.readouterr().out
    path = tmp_path / "reviewed.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    assert cli.main(args + ["--plan-file", str(path), "--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert cli.main(args + ["--restore", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["voice_direction"]["human_reviewed"] is True
