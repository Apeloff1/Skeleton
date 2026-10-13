"""Dialogue player visibility, witnessed choices and editor-only unlock diagnostics."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from core.branching_narrative import SCHEMA, validate_plan
from core.dialogue_projection import SCHEMA as DIALOGUE_SCHEMA, project_dialogue


def source_plan():
    def ending(key, tone, secret):
        return {
            "id": key, "title": "The " + key + " fate", "tone": tone,
            "epilogue": "The story closes on " + secret + " and the city's history is changed.",
            "consequences": "The world remembers the irrevocable charter decision.",
            "character_conclusions": {}, "place_conclusions": {},
            "quest_conclusions": {}, "faction_conclusions": {}, "required_lore": [],
        }

    def option(key, label, *, next_node=None, ending_id=None, guard=None, effects=None):
        return {
            "id": key, "label": label, "dialogue": "I choose " + label,
            "intent": "The decision changes the city's long-term history.",
            "emotional_consequence": "The player's friends remember the decision.",
            "guard": guard or {"op": "always"}, "effects": effects or [],
            "next_node": next_node, "ending": ending_id,
        }

    return {
        "schema_version": SCHEMA, "title": "City of Hidden Oaths",
        "branch_id": "main", "entry_node": "arrival",
        "initial_state": {}, "characters": [], "places": [],
        "nodes": [
            {"id": "arrival", "scene": 1, "act": 1, "chapter": 1,
             "kind": "quest", "speaker": None, "place": None,
             "text": "The city arrival begins before dawn.",
             "plot_points": [{"id": "arrival_beat", "anchor": "before dawn"}],
             "options": [
                 option("decline", "decline the clue", next_node="crossroads"),
                 option("learn", "study the clue", next_node="crossroads",
                        effects=[{"op": "flag_set", "id": "secret_knowledge"}]),
             ]},
            {"id": "crossroads", "scene": 2, "act": 1, "chapter": 1,
             "kind": "dialogue" if False else "quest",
             "speaker": None, "place": None,
             "text": "The gatekeeper offers a visible peaceful treaty.",
             "plot_points": [{"id": "treaty", "anchor": "peaceful treaty"}],
             "options": [
                 option("treaty_choice", "accept peace", ending_id="peace"),
                 option("shadow_choice", "reach the SHADOW_VAULT_99",
                        ending_id="shadow",
                        guard={"op": "all", "items": [
                            {"op": "flag", "id": "secret_knowledge"},
                            {"op": "meter", "kind": "karma",
                             "comparison": "gte", "value": 0},
                        ]}),
             ]},
        ],
        "endings": [
            ending("peace", "good", "peace"),
            ending("shadow", "evil", "UNREACHED_SECRET_DESTINY_99"),
        ],
    }


def test_player_view_does_not_leak_hidden_dialogue_targets_guards_or_endings():
    plan = validate_plan(source_plan())
    projection = project_dialogue(plan, ["decline"])
    assert projection["schema_version"] == DIALOGUE_SCHEMA
    assert projection["scene"] == 2
    assert [o["id"] for o in projection["available_replies"]] == ["treaty_choice"]
    assert projection["ending"] is None
    assert projection["simulation_only"]
    assert projection["content_trust"].startswith("creator_authored_untrusted")
    assert projection["history_tail"][0]["choice_id"] == "decline"
    encoded = json.dumps(projection)
    for secret in ("shadow_choice", "SHADOW_VAULT_99",
                   "UNREACHED_SECRET_DESTINY_99", "secret_knowledge",
                   "locked_choices", "next_node", "guard"):
        assert secret not in encoded


def test_creator_diagnostics_require_explicit_mode_and_bind_exact_history():
    plan = validate_plan(source_plan())
    player = project_dialogue(plan, ["decline"])
    author = project_dialogue(plan, ["decline"], creator_diagnostics=True)
    assert author["playthrough_receipt"] == player["playthrough_receipt"]
    assert author["projection_digest"] != player["projection_digest"]
    assert author["creator_diagnostics_only"]
    assert len(author["locked_choices"]) == 1
    assert author["locked_choices"][0]["id"] == "shadow_choice"
    missing = author["locked_choices"][0]["unmet"]
    assert missing["op"] == "all" and len(missing["missing"]) == 1
    assert missing["missing"][0]["id"] == "secret_knowledge"
    unlocked = project_dialogue(plan, ["learn"], creator_diagnostics=True)
    assert len(unlocked["locked_choices"]) == 0
    assert {o["id"] for o in unlocked["available_replies"]} == {
        "treaty_choice", "shadow_choice",
    }
    assert unlocked["playthrough_receipt"] != player["playthrough_receipt"]


def test_playthrough_cannot_select_locked_option_and_never_mutates_source():
    plan = validate_plan(source_plan())
    before = deepcopy(plan)
    with pytest.raises(ValueError, match="unavailable"):
        project_dialogue(plan, ["decline", "shadow_choice"])
    assert plan == before
    ending = project_dialogue(plan, ["learn", "shadow_choice"])
    assert ending["ending_reached"] and ending["ending_accepted"]
    assert ending["ending"]["id"] == "shadow"
    assert "UNREACHED_SECRET_DESTINY_99" in ending["ending"]["epilogue"]
    assert ending["available_replies"] == []
    assert "peaceful treaty" not in json.dumps(ending)
    assert project_dialogue(plan, ["learn", "shadow_choice"]) == ending


def test_full_scene_is_bounded_and_truncation_is_truthfully_reported():
    draft = source_plan()
    draft["nodes"][0]["text"] = "before dawn " + ("x" * 8000)
    plan = validate_plan(draft)
    projected = project_dialogue(plan, [])
    assert projected["scene_text_truncated"]
    assert len(projected["scene_text"]) == 5000
    assert projected["history_truncated"] is False
    assert len(projected["projection_digest"]) == 64


def test_nested_boolean_lock_diagnostics_never_present_as_player_copy():
    plan_raw = source_plan()
    guarded = plan_raw["nodes"][1]["options"][1]
    guarded["guard"] = {"op": "any", "items": [
        {"op": "not", "item": {"op": "always"}},
        {"op": "all", "items": [
            {"op": "flag", "id": "secret_knowledge"},
            {"op": "quest", "id": "guild_initiation", "state": "completed"},
        ]},
    ]}
    plan = validate_plan(plan_raw)
    editor = project_dialogue(plan, ["decline"], creator_diagnostics=True)
    blocked = editor["locked_choices"][0]["unmet"]
    assert blocked["op"] == "any"
    assert blocked["alternatives"][0]["op"] == "not"
    assert blocked["alternatives"][1]["missing"][1]["id"] == "guild_initiation"
    assert "guild_initiation" not in json.dumps(project_dialogue(plan, ["decline"]))
