"""Cross-vertical original quest voice/chronology playable handoff tests."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_character_locale import (
    compile_quest_character_locale_handoff,
)
from skeleton.ai.game_builder.studio_quest_voice_direction import (
    PROMPT as VOICE_PROMPT, propose_voice_direction, compile_voice_direction,
)
from skeleton.ai.game_builder.studio_quest_chronology import (
    PROMPT as CHRONO_PROMPT, propose_quest_chronology, compile_quest_chronology,
)
from skeleton.ai.game_builder.studio_quest_performance_timeline import (
    PROMPT, FILENAME, propose_performance_timeline, compile_performance_timeline,
    replay_performance_timeline, publish_performance_timeline,
    restore_performance_timeline, render_performance_timeline_html,
    render_performance_timeline_editor,
)
from tests.test_studio_quest_character_locale import fixture


def prepared():
    parts = fixture()
    documents = parts[0]
    base = compile_quest_character_locale_handoff(*parts, authorized=True)
    voice_plan = propose_voice_direction(
        documents, *parts[1:], prompt=VOICE_PROMPT,
        expected_handoff_digest=base["handoff_digest"], authorized=True)
    for row in voice_plan["rows"]:
        row["reviewed"] = True
    voice = compile_voice_direction(
        documents, *parts[1:], plan=voice_plan,
        expected_handoff_digest=base["handoff_digest"], authorized=True)
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    actions = [[event["stage_id"], event["choice"]] for event in base["events"]]
    chrono_plan = propose_quest_chronology(
        documents, CHRONO_PROMPT, actions, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    for row in chrono_plan["rows"]:
        row["reviewed"] = True
    chronology = compile_quest_chronology(
        documents, chrono_plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    kwargs = {"voice_receipt": voice, "chronology_receipt": chronology}
    plan = propose_performance_timeline(
        documents, *parts[1:], prompt=PROMPT,
        expected_voice_digest=voice["voice_direction_digest"],
        expected_chronology_digest=chronology["chronology_digest"],
        authorized=True, **kwargs)
    for row in plan["rows"]:
        row["reviewed"] = True
    return parts, kwargs, plan


def compile_checked(parts, kwargs, plan):
    return compile_performance_timeline(
        parts[0], *parts[1:], plan=plan,
        expected_voice_digest=kwargs["voice_receipt"]["voice_direction_digest"],
        expected_chronology_digest=kwargs["chronology_receipt"]["chronology_digest"],
        authorized=True, **kwargs)


def test_cross_vertical_verified_handoff_and_preview():
    parts, kwargs, plan = prepared()
    result = compile_checked(parts, kwargs, plan)
    assert result["canonical_quest_replay_verified"] is True
    assert result["authored_window_fit_verified"] is True
    assert result["estimated_not_observed"] is True
    assert result["audio_generated"] is False
    assert result["native_gameplay_verified"] is False
    assert all(x["remaining_ms"] >= 0 for x in result["timeline"])
    assert replay_performance_timeline(
        parts[0], *parts[1:], receipt=result, authorized=True, **kwargs) == result
    html = render_performance_timeline_html(
        parts[0], *parts[1:], receipt=result, authorized=True, **kwargs)
    assert b"Content-Security-Policy" in html
    assert b"no observed speech" in html
    editor = render_performance_timeline_editor(
        parts[0], *parts[1:], plan=plan, authorized=True, **kwargs)
    assert b"Export edited performance plan" in editor
    assert b"connect-src 'none'" in editor


def test_reject_stale_source_wrong_session_and_forged_cues():
    parts, kwargs, plan = prepared()
    changed = copy.deepcopy(kwargs)
    changed["voice_receipt"]["voice_direction_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_checked(parts, changed, plan)
    changed = copy.deepcopy(kwargs)
    changed["chronology_receipt"]["session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_checked(parts, changed, plan)
    changed = copy.deepcopy(plan)
    changed["rows"][0]["stage_id"] = "forged"
    with pytest.raises(StudioQuestError, match="identity"):
        compile_checked(parts, kwargs, changed)
    changed = copy.deepcopy(plan)
    changed["rows"][0]["buffer_ms"] = True
    with pytest.raises(StudioQuestError):
        compile_checked(parts, kwargs, changed)


def test_reject_unreviewed_or_oversubscribed_window():
    parts, kwargs, plan = prepared()
    changed = copy.deepcopy(plan)
    changed["rows"][0]["reviewed"] = False
    with pytest.raises(StudioQuestError, match="reviewed"):
        compile_checked(parts, kwargs, changed)
    changed = copy.deepcopy(plan)
    changed["rows"][0]["buffer_ms"] = 30001
    with pytest.raises(StudioQuestError):
        compile_checked(parts, kwargs, changed)
    changed = copy.deepcopy(kwargs)
    changed["chronology_receipt"]["timeline"][0]["duration_minutes"] = 0
    with pytest.raises(StudioQuestError):
        compile_checked(parts, changed, plan)


def test_private_publish_restore_tamper_symlink(tmp_path):
    parts, kwargs, plan = prepared()
    checked = compile_checked(parts, kwargs, plan)
    result = publish_performance_timeline(
        parts[0], *parts[1:], receipt=checked, directory=tmp_path,
        authorized=True, **kwargs)
    assert result["file_write_performed"] is True
    assert restore_performance_timeline(
        parts[0], *parts[1:], directory=tmp_path,
        authorized=True, **kwargs) == checked
    with pytest.raises(FileExistsError):
        publish_performance_timeline(
            parts[0], *parts[1:], receipt=checked, directory=tmp_path,
            authorized=True, **kwargs)
    target = tmp_path / FILENAME
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises((OSError, StudioQuestError)):
        restore_performance_timeline(
            parts[0], *parts[1:], directory=tmp_path,
            authorized=True, **kwargs)
    target.unlink()
    target.write_text(json.dumps({**checked, "estimated_not_observed": False}))
    os.chmod(target, 0o600)
    with pytest.raises(StudioQuestError):
        restore_performance_timeline(
            parts[0], *parts[1:], directory=tmp_path,
            authorized=True, **kwargs)


def test_cli_plan_compile_publish_and_restore(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_performance_timeline_cli as cli
    parts, kwargs, plan = prepared()
    monkeypatch.setattr(cli, "read_blueprint", lambda _: parts[0])
    args = ["--project", "original_demo"]
    fields = ("branch", "npc", "dialogue", "dialogue-locale",
              "localization", "achievements", "pacing", "advisories")
    for field, value in zip(fields, parts[1:-1]):
        path = tmp_path / (field + ".json")
        path.write_text(json.dumps(value))
        os.chmod(path, 0o600)
        args += ["--" + field + "-file", str(path)]
    args += ["--accept-topic", "loud_audio"]
    for key, arg in (("voice_receipt", "--voice-file"),
                     ("chronology_receipt", "--chronology-file")):
        path = tmp_path / (key + ".json")
        path.write_text(json.dumps(kwargs[key]))
        os.chmod(path, 0o600)
        args += [arg, str(path)]
    assert cli.main(args) == 0
    proposed = json.loads(capsys.readouterr().out)["plan"]
    assert proposed["rows"][0]["reviewed"] is False
    assert cli.main(args + ["--editor-html"]) == 0
    assert "Export edited performance plan" in capsys.readouterr().out
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))
    os.chmod(plan_file, 0o600)
    assert cli.main(args + ["--plan-file", str(plan_file),
                            "--publish", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["file_write_performed"] is True
    assert cli.main(args + ["--restore", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["performance_timeline"][
        "release_certified"] is False
