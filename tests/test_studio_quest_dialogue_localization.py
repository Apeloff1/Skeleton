"""NPC dialogue translations preserve original canonical identities."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_dialogue_localization import (
    FILENAME, PROMPT, propose_dialogue_localization,
    compile_dialogue_localization, replay_dialogue_localization,
    compile_dialogue_localized_handoff, publish_dialogue_localization,
    restore_dialogue_localization, render_dialogue_localization_editor_html,
)
from tests.test_studio_quest_dialogue import (
    make_dialogue, review, compile_plan_dialogue,
)


def fixture():
    docs, program, initial, npc, dialogue_plan = make_dialogue()
    dialogue = compile_plan_dialogue(
        docs, program, initial, npc, review(dialogue_plan))
    plan = propose_dialogue_localization(
        docs, npc, dialogue, PROMPT, "fr-FR", authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    return docs, program, initial, npc, dialogue, plan


def compile_plan(docs, program, initial, npc, dialogue, plan):
    return compile_dialogue_localization(
        docs, npc, dialogue, plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)


def test_reviewed_translation_handoff_preserves_canonical_choice():
    docs, program, initial, npc, dialogue, plan = fixture()
    draft = compile_plan(docs, program, initial, npc, dialogue, plan)
    assert draft["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_dialogue_localized_handoff(
            docs, npc, dialogue, draft, authorized=True)
    for row in plan["rows"]:
        row["translation"] = "Une phrase originale"
        row["reviewed"] = True
    receipt = compile_plan(docs, program, initial, npc, dialogue, plan)
    handoff = compile_dialogue_localized_handoff(
        docs, npc, dialogue, receipt, authorized=True)
    assert handoff["locale"] == "fr-FR"
    assert handoff["canonical_choices"] == [["gate", "help"], ["harbor", "sail"]]
    assert handoff["localized_dialogue_lines"][0]["speaker"] == "captain"
    assert handoff["localized_dialogue_lines"][0]["display"] == "Une phrase originale"
    assert handoff["translation_provenance_verified"] is False
    assert handoff["release_certified"] is False


@pytest.mark.parametrize("field,value", [
    ("speaker", "forged"), ("source_text", "forged original"),
    ("stage_id", "unknown"), ("choice", "fake"),
    ("beat_index", 1), ("reviewed", 1),
    ("translation", ""), ("translation", "bad\nline"),
])
def test_changed_identity_and_invalid_review_rejected(field, value):
    docs, program, initial, npc, dialogue, plan = fixture()
    plan["rows"][0][field] = value
    with pytest.raises((StudioQuestError, ValueError)):
        compile_plan(docs, program, initial, npc, dialogue, plan)


def test_locale_and_coverage_are_exact():
    docs, program, initial, npc, dialogue, plan = fixture()
    plan["locale"] = "invalid_locale"
    with pytest.raises(StudioQuestError):
        compile_plan(docs, program, initial, npc, dialogue, plan)
    plan = fixture()[5]
    plan["rows"].pop()
    with pytest.raises(StudioQuestError):
        compile_plan(docs, program, initial, npc, dialogue, plan)


def test_forged_receipt_and_stale_dialogue_fail():
    docs, program, initial, npc, dialogue, plan = fixture()
    for row in plan["rows"]:
        row["reviewed"] = True
    receipt = compile_plan(docs, program, initial, npc, dialogue, plan)
    forged = copy.deepcopy(receipt)
    forged["authoring"]["rows"][0]["translation"] = "forged"
    with pytest.raises(StudioQuestError):
        replay_dialogue_localization(docs, npc, dialogue, forged, authorized=True)
    changed = copy.deepcopy(dialogue)
    changed["authoring"]["lines"][0]["text"] = "forged original"
    with pytest.raises(StudioQuestError):
        replay_dialogue_localization(docs, npc, changed, receipt, authorized=True)
    with pytest.raises(PermissionError):
        replay_dialogue_localization(docs, npc, dialogue, receipt, authorized=False)


def test_private_publish_restore_and_symlink(tmp_path):
    docs, program, initial, npc, dialogue, plan = fixture()
    for row in plan["rows"]:
        row["reviewed"] = True
    receipt = compile_plan(docs, program, initial, npc, dialogue, plan)
    result = publish_dialogue_localization(
        docs, npc, dialogue, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_dialogue_localization(
        docs, npc, dialogue, tmp_path, authorized=True,
        expected_source_digest=program.source_digest) == receipt
    with pytest.raises(FileExistsError):
        publish_dialogue_localization(
            docs, npc, dialogue, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_dialogue_localization(
            docs, npc, dialogue, tmp_path, authorized=True,
            expected_source_digest=program.source_digest)


def test_editor_csp_and_cli_handoff(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_dialogue_localization_cli as cli
    docs, program, initial, npc, dialogue, plan = fixture()
    for row in plan["rows"]:
        row["translation"] = "</script><img src=x>"
        row["reviewed"] = True
    receipt = compile_plan(docs, program, initial, npc, dialogue, plan)
    html = render_dialogue_localization_editor_html(
        docs, npc, dialogue, receipt, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"\\u003c/script>" in html
    assert b"</script><img" not in html
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    paths = []
    for i, payload in enumerate((npc, dialogue, plan)):
        path = tmp_path / (str(i) + ".json")
        path.write_text(json.dumps(payload))
        os.chmod(path, 0o600)
        paths.append(path)
    assert cli.main([
        "--project", "branch_demo", "--npc-file", str(paths[0]),
        "--dialogue-file", str(paths[1]), "--plan", str(paths[2]),
        "--handoff",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["playable_handoff"]["locale"] == "fr-FR"
