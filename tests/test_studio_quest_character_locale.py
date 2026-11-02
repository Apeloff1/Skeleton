"""Locale-consistent character experience integration and fail-closed replay."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_dialogue_localization import (
    PROMPT, propose_dialogue_localization, compile_dialogue_localization,
)
from skeleton.ai.game_builder.studio_quest_character_locale import (
    FILENAME, compile_quest_character_locale_handoff,
    render_quest_character_locale_html, publish_quest_character_locale,
    restore_quest_character_locale,
)
from tests.test_studio_quest_character_experience import fixture as character_fixture


def fixture():
    parts = character_fixture()
    docs, branch, npc, dialogue, loc, awards, pace, warnings, topics = parts
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_dialogue_localization(
        docs, npc, dialogue, PROMPT, "en-US", **leases)
    for row in plan["rows"]:
        row["translation"] = "A reviewed localized original line"
        row["reviewed"] = True
    locale = compile_dialogue_localization(docs, npc, dialogue, plan, **leases)
    return (docs, branch, npc, dialogue, locale, loc, awards, pace, warnings, topics)


def test_full_localized_character_handoff_preserves_quest_and_trust():
    parts = fixture()
    handoff = compile_quest_character_locale_handoff(
        *parts, authorized=True)
    assert handoff["locale"] == "en-US"
    assert handoff["events"][0]["dialogue"][0]["display"] == (
        "A reviewed localized original line")
    assert handoff["events"][0]["npc_trust_effects"][0]["after"] == 5
    assert handoff["final_trust"] == [{"actor_id": "guide", "trust": 5}]
    assert handoff["translation_provenance_verified"] is False
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False


def test_mixed_locale_and_stale_translation_fail():
    parts = list(fixture())
    docs, _, npc, dialogue = parts[:4]
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_dialogue_localization(
        docs, npc, dialogue, PROMPT, "fr-FR", **leases)
    for row in plan["rows"]:
        row["reviewed"] = True
    parts[4] = compile_dialogue_localization(docs, npc, dialogue, plan, **leases)
    with pytest.raises(StudioQuestError, match="mixed stage"):
        compile_quest_character_locale_handoff(*parts, authorized=True)
    parts = list(fixture())
    parts[4]["authoring"]["rows"][0]["translation"] = "Forged"
    with pytest.raises(StudioQuestError):
        compile_quest_character_locale_handoff(*parts, authorized=True)


def test_missing_consent_and_wrong_source_fail():
    parts = list(fixture())
    parts[-1] = []
    with pytest.raises(StudioQuestError):
        compile_quest_character_locale_handoff(*parts, authorized=True)
    parts = list(fixture())
    parts[0]["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        compile_quest_character_locale_handoff(*parts, authorized=True)


def test_private_publication_restore_and_symlink(tmp_path):
    parts = fixture()
    result = publish_quest_character_locale(
        *parts, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_quest_character_locale(
        *parts, tmp_path, authorized=True)["handoff_digest"] == result["handoff_digest"]
    with pytest.raises(FileExistsError):
        publish_quest_character_locale(*parts, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_character_locale(*parts, tmp_path, authorized=True)


def test_html_escapes_and_cli_roundtrip(tmp_path, capsys, monkeypatch):
    from scripts import studio_quest_character_locale_cli as cli
    parts = fixture()
    html = render_quest_character_locale_html(*parts, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"Localized original character replay" in html
    monkeypatch.setattr(cli, "read_blueprint", lambda _: parts[0])
    fields = ("branch", "npc", "dialogue", "dialogue-locale",
              "localization", "achievements", "pacing", "advisories")
    args = ["--project", "original_demo"]
    for field, payload in zip(fields, parts[1:-1]):
        path = tmp_path / (field + ".json")
        path.write_text(json.dumps(payload))
        os.chmod(path, 0o600)
        args.extend(["--" + field + "-file", str(path)])
    args.extend(["--accept-topic", "loud_audio"])
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["playable_handoff"]["locale"] == "en-US"
