"""Quest presentation assembly: cross-vertical session parity and secure preview."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_localization import (
    PROMPT as LOCALE_PROMPT, propose_quest_localization,
    compile_quest_localization,
)
from skeleton.ai.game_builder.studio_quest_achievements import (
    PROMPT as AWARD_PROMPT, propose_quest_achievements,
    compile_quest_achievements,
)
from skeleton.ai.game_builder.studio_quest_presentation_bundle import (
    compile_quest_presentation_bundle, compile_quest_presentation_handoff,
    render_quest_presentation_preview_html,
)

PROJECT = "studio_puzzle_expedition_copper_mesa"


def fixture():
    docs = read_blueprint(PROJECT)
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    actions = [[program.stages[0].key, program.stages[0].alternatives[0]]]
    target = program.endings[0][0]
    locale = propose_quest_localization(
        docs, LOCALE_PROMPT, "nb-NO", actions, target, **leases)
    awards = propose_quest_achievements(
        docs, AWARD_PROMPT, actions, target_ending=target, **leases)
    return docs, compile_quest_localization(docs, locale, **leases), \
        compile_quest_achievements(docs, awards, **leases), leases


def test_cross_vertical_replay_and_held_handoff():
    docs, locale, awards, _ = fixture()
    bundle = compile_quest_presentation_bundle(
        docs, locale, awards, authorized=True)
    assert bundle["source_digest"] == locale["source_digest"]
    assert bundle["session_digest"] == awards["session_digest"]
    assert bundle["sandbox_points"] == awards["sandbox_points"]
    assert bundle["playable_handoff_allowed"] is False
    assert bundle["release_certified"] is False
    with pytest.raises(StudioQuestError):
        compile_quest_presentation_handoff(
            docs, locale, awards, authorized=True)


def test_forged_and_mismatched_receipts_fail_closed():
    docs, locale, awards, _ = fixture()
    forged = copy.deepcopy(awards)
    forged["sandbox_points"] += 100
    with pytest.raises(StudioQuestError):
        compile_quest_presentation_bundle(
            docs, locale, forged, authorized=True)
    with pytest.raises(PermissionError):
        compile_quest_presentation_bundle(
            docs, locale, awards, authorized=False)
    forged = copy.deepcopy(locale)
    forged["session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        compile_quest_presentation_bundle(
            docs, forged, awards, authorized=True)


def test_readonly_html_is_escaped_and_csp_network_disabled():
    docs, locale, awards, _ = fixture()
    html = render_quest_presentation_preview_html(
        docs, locale, awards, authorized=True)
    assert b"default-src 'none'" in html
    assert b"<script" not in html
    assert b"Original quest presentation review" in html
    assert b"unlocked" in html


def test_cli_requires_private_receipts_and_exact_leases(tmp_path, capsys):
    from scripts.studio_quest_presentation_bundle_cli import main
    docs, locale, awards, leases = fixture()
    local_path = tmp_path / "locale.json"
    award_path = tmp_path / "awards.json"
    local_path.write_text(json.dumps(locale))
    award_path.write_text(json.dumps(awards))
    os.chmod(local_path, 0o600)
    os.chmod(award_path, 0o600)
    args = ["--project", PROJECT, "--localization-file", str(local_path),
            "--achievements-file", str(award_path), "--expected-source",
            leases["expected_source_digest"], "--expected-session",
            leases["expected_initial_session_digest"]]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["bundle"]["playable_handoff_allowed"] is False
    assert main(args + ["--preview-html"]) == 0
    assert "Original quest presentation review" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(args + ["--handoff"])
    with pytest.raises(SystemExit):
        main(args[:-1] + ["0" * 64])


def test_complete_reviewed_eligible_quest_produces_verified_playable_bundle():
    """A minimal original quest proves the successful end-user handoff path."""
    docs = {
        "quest": {
            "project_id": "original_copper_garden",
            "release_certified": False,
            "stages": [{
                "id": "plant_seed", "alternatives": ["plant", "wait"],
                "reward": "garden_bloom",
                "choice_effects": {
                    "plant": ["choice:plant_seed:grew_garden"],
                    "wait": ["choice:plant_seed:rested"],
                },
            }],
        },
        "narrative": {
            "project_id": "original_copper_garden",
            "release_certified": False,
            "endings": [{
                "id": "garden_restored",
                "requires": ["choice:plant_seed:grew_garden"],
            }],
        },
    }
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    leases = {
        "authorized": True,
        "expected_source_digest": program.source_digest,
        "expected_initial_session_digest": initial.digest,
    }
    actions = [["plant_seed", "plant"]]
    locale_plan = propose_quest_localization(
        docs, LOCALE_PROMPT, "nb-NO", actions, "garden_restored", **leases)
    for row in locale_plan["rows"]:
        row["reviewed"] = True
        if row["source"] == "plant":
            row["translation"] = "plante"
    achievement_plan = propose_quest_achievements(
        docs, AWARD_PROMPT, actions, target_ending="garden_restored", **leases)
    achievement_plan["achievements"][0]["required_choice"] = "plant"
    achievement_plan["achievements"][0]["required_effect"] = (
        "choice:plant_seed:grew_garden")
    locale = compile_quest_localization(docs, locale_plan, **leases)
    awards = compile_quest_achievements(docs, achievement_plan, **leases)
    bundle = compile_quest_presentation_bundle(
        docs, locale, awards, authorized=True)
    assert bundle["playable_handoff_allowed"] is True
    handoff = compile_quest_presentation_handoff(
        docs, locale, awards, authorized=True)
    assert handoff["canonical_choices"] == actions
    assert handoff["target_ending"] == "garden_restored"
    assert handoff["unlocked_achievements"][0]["id"] == "stage_1"
    assert handoff["sandbox_points"] == 10
    assert any(row["display"] == "plante" and row["source"] == "plant"
               for row in handoff["localized_display_rows"])
    assert handoff["native_gameplay_verified"] is False
    assert handoff["release_certified"] is False
    html = render_quest_presentation_preview_html(
        docs, locale, awards, authorized=True)
    assert b"plante" in html
    assert b"Handoff allowed: yes" in html
    assert b"<script" not in html
    tampered = copy.deepcopy(locale)
    tampered["authoring"]["rows"][0]["translation"] = "forged"
    with pytest.raises(StudioQuestError):
        compile_quest_presentation_handoff(
            docs, tampered, awards, authorized=True)
