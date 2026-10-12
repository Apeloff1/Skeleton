"""Large-scale branching adventure regression: karma, location/faction reputation,
quest completion/missed/failure, dialogue, lore, separate NPC endings and closure.
"""
from __future__ import annotations
from copy import deepcopy
import pytest

from core.branching_narrative import (
    SCHEMA, validate_plan, simulate, audit_outcomes,
    validate_condition, initial_state, holds, apply_effects,
)


def actor():
    return {
        "id": "aria", "name": "Aria", "source_scene": 1,
        "backstory": "A courier whose family was displaced by a mining war.",
        "goals": "Recover the ancestral compass and restore the lost charter.",
        "dialogue_style": "Careful, wary, eloquent under pressure.",
        "personal_ending": "The epilogue must show what becomes of Aria.",
        "relationships": [], "factions": ["council"], "known_secrets": [],
        "plot_threads": ["compass"],
    }


def place():
    return {
        "id": "glass_city", "name": "Glass City", "source_scene": 1,
        "kind": "city", "history": "Founded above an ancient observatory.",
        "culture": "Glassmakers trade relics for community protection.",
        "regional_conflicts": "The council and smugglers contest the market.",
        "factions": ["council", "gang"], "plot_threads": ["compass"],
        "discovered_by": ["aria"],
    }


def option(key, label, *, guard=None, effects=None, next_node=None, ending=None):
    return {
        "id": key, "label": label, "dialogue": "Aria, " + label,
        "intent": "Choose the fate of the city and honor the hero's role.",
        "emotional_consequence": "The relationship and city state change visibly.",
        "guard": guard or {"op": "always"}, "effects": effects or [],
        "next_node": next_node, "ending": ending,
    }


def threat(role, point):
    return {"op": "thread", "id": "compass", "role": role, "plot_id": point}


def score(delta):
    return {"op": "meter_delta", "kind": "karma", "delta": delta}


def reputation(group, delta, scope="faction"):
    return {"op": "meter_delta", "kind": "reputation", "scope": scope,
            "subject": group, "delta": delta}


def ending(name, tone):
    return {
        "id": name, "title": name.replace("_", " ").title(), "tone": tone,
        "epilogue": "The epilogue shows that Aria carries forward the truth and the city lives with this consequence.",
        "consequences": "Power, trade, personal trust and future quests are changed irreversibly.",
        "character_conclusions": {"aria": "Aria's family gains a new purpose and her loyalties are remembered."},
        "place_conclusions": {"glass_city": "The city's public history and institutions change."},
        "quest_conclusions": {"retrieve_compass": "The compass quest result is acknowledged by survivors."},
        "faction_conclusions": {"council": "The council remembers the player's stance.",
                                "gang": "The gang records the player's support or opposition."},
        "required_lore": [],
    }


def plan():
    return {
        "schema_version": SCHEMA, "title": "The Compass of Glass City",
        "branch_id": "main", "entry_node": "opening",
        "characters": [actor()], "places": [place()],
        "initial_state": {},
        "nodes": [
            {
                "id": "opening", "scene": 1, "act": 1, "chapter": 1,
                "kind": "dialogue", "speaker": "aria", "place": "glass_city",
                "text": "Aria whispers: the compass sleeps under the market, beyond the guards.",
                "plot_points": [{"id": "secret", "anchor": "compass sleeps under the market"}],
                "options": [
                    option("help_aria", "Help Aria and protect the market.", next_node="junction",
                           effects=[score(40), reputation("council", 30),
                                    {"op": "quest_set", "id": "retrieve_compass", "state": "active"},
                                    threat("setup", "secret"),
                                    {"op": "lore_discover", "id": "ancient_observatory"}]),
                    option("side_with_gang", "Deliver the city to the smugglers.", next_node="junction",
                           effects=[score(-60), reputation("gang", 40),
                                    reputation("glass_city", -15, "city"),
                                    {"op": "quest_set", "id": "retrieve_compass", "state": "failed"},
                                    threat("setup", "secret")]),
                    option("walk_away", "Remain neutral and leave the quest missed.", next_node="junction",
                           effects=[{"op": "quest_set", "id": "retrieve_compass", "state": "missed"},
                                    threat("setup", "secret")]),
                ],
            },
            {
                "id": "junction", "scene": 2, "act": 1, "chapter": 1,
                "kind": "dialogue", "speaker": "aria", "place": "glass_city",
                "text": "Aria reveals: the compass belongs to the city's original founders.",
                "plot_points": [{"id": "truth", "anchor": "compass belongs to the city's original founders"}],
                "options": [
                    option("good_ending", "Return the relic and restore the charter.",
                           ending="restoration",
                           guard={"op": "all", "items": [
                               {"op": "meter", "kind": "karma", "comparison": "gte", "value": 20},
                               {"op": "quest", "id": "retrieve_compass", "state": "active"},
                               {"op": "lore", "id": "ancient_observatory"},
                           ]},
                           effects=[{"op": "quest_set", "id": "retrieve_compass", "state": "completed"},
                                    threat("payoff", "truth")]),
                    option("evil_ending", "Sell the charter to the gangs.",
                           ending="ruin",
                           guard={"op": "meter", "kind": "karma", "comparison": "lte", "value": -20},
                           effects=[threat("resolution", "truth")]),
                    option("neutral_ending", "Let the factions negotiate a fragile peace.",
                           ending="truce",
                           guard={"op": "meter", "kind": "karma", "comparison": "eq", "value": 0},
                           effects=[threat("resolution", "truth")]),
                ],
            },
        ],
        "endings": [ending("restoration", "good"), ending("ruin", "evil"),
                    ending("truce", "neutral")],
    }


def test_three_distinct_gated_endings_are_reachable_from_real_player_histories():
    compiled = validate_plan(plan())
    assert len(compiled["endings"]) == 3
    good = simulate(compiled, ["help_aria", "good_ending"])
    evil = simulate(compiled, ["side_with_gang", "evil_ending"])
    neutral = simulate(compiled, ["walk_away", "neutral_ending"])
    assert [x["ending"]["tone"] for x in (good, neutral, evil)] == [
        "good", "neutral", "evil",
    ]
    assert all(x["ending_accepted"] for x in [good, neutral, evil])
    assert good["state"]["quests"]["retrieve_compass"] == "completed"
    assert evil["state"]["quests"]["retrieve_compass"] == "failed"
    assert neutral["state"]["quests"]["retrieve_compass"] == "missed"
    assert good["state"]["meters"]["karma"] == 40
    assert evil["state"]["meters"]["karma"] == -60
    assert evil["state"]["meters"]["reputation:faction:gang"] == 40
    assert evil["state"]["meters"]["reputation:city:glass_city"] == -15
    assert len({good["receipt_digest"], neutral["receipt_digest"],
                evil["receipt_digest"]}) == 3
    assert all(len(x["steps"]) == 2 for x in [good, neutral, evil])


def test_dialogue_unlocks_only_genuine_state_satisfied_options():
    compiled = validate_plan(plan())
    start = simulate(compiled, [])
    assert {x["id"] for x in start["available_options"]} == {
        "help_aria", "side_with_gang", "walk_away",
    }
    mid = simulate(compiled, ["help_aria"])
    assert [x["id"] for x in mid["available_options"]] == ["good_ending"]
    with pytest.raises(ValueError, match="unavailable"):
        simulate(compiled, ["walk_away", "good_ending"])


def test_real_guarded_paths_are_exhaustive_at_small_scale():
    compiled = validate_plan(plan())
    result = audit_outcomes(compiled, max_paths=200)
    assert result["complete"] is True
    assert result["all_paths_verified"] is True
    assert result["reachable_endings"] == ["restoration", "ruin", "truce"]
    assert result["dead_end_paths"] == 0
    assert result["issue_count"] == 0
    limited = audit_outcomes(compiled, max_paths=1)
    assert limited["complete"] is False
    assert limited["all_paths_verified"] is False


def test_faction_lore_and_personal_ending_must_conclude_for_every_visited_actor():
    broken = plan()
    broken["endings"][0]["character_conclusions"] = {}
    broken["endings"][0]["place_conclusions"] = {}
    broken["endings"][0]["quest_conclusions"] = {}
    broken["endings"][0]["faction_conclusions"] = {}
    current = simulate(validate_plan(broken), ["help_aria", "good_ending"])
    assert current["ending_accepted"] is False
    assert current["unresolved_character_arcs"] == ["aria"]
    assert current["unresolved_place_lore"] == ["glass_city"]
    assert current["unresolved_quest_conclusions"] == ["retrieve_compass"]
    assert current["unresolved_faction_conclusions"] == ["council"]


def test_red_herring_is_allowed_but_must_be_disclosed_not_generic_resolved():
    raw = plan()
    raw["nodes"][0]["options"][0]["effects"][-2] = threat("red_herring", "secret")
    compiled = validate_plan(raw)
    with pytest.raises(ValueError, match="red herring"):
        simulate(compiled, ["help_aria", "good_ending"])
    raw["nodes"][1]["options"][0]["effects"][-1] = threat("false_lead_disclosed", "truth")
    successful = simulate(validate_plan(raw), ["help_aria", "good_ending"])
    assert successful["ending_accepted"]


def test_disabled_choice_paths_diagnosed_as_no_available_choices():
    raw = plan()
    raw["nodes"][1]["options"][2]["guard"] = {
        "op": "quest", "id": "retrieve_compass", "state": "completed",
    }
    compiled = validate_plan(raw)
    incomplete = audit_outcomes(compiled, max_paths=100)
    assert incomplete["all_paths_verified"] is False
    assert incomplete["dead_end_paths"] == 1
    assert "truce" in incomplete["unreachable_endings"]


def test_guard_depth_fails_closed_without_interpreter_or_eval():
    tree = {"op": "always"}
    for _ in range(10):
        tree = {"op": "not", "item": tree}
    with pytest.raises(ValueError, match="deep"):
        validate_condition(tree)
    for guard in [{"op": "python", "script": "os.system('...')"},
                  {"op": "meter", "kind": "karma", "comparison": "gte", "value": "100"},
                  {"op": "meter", "kind": "reputation", "scope": "planet", "subject": "x",
                   "comparison": "gte", "value": 3}]:
        with pytest.raises(ValueError):
            validate_condition(guard)


def test_terminal_quest_status_cannot_be_silently_rewritten():
    current = initial_state({"quests": {"quest": "missed"}})
    with pytest.raises(ValueError, match="cannot be silently rewritten"):
        apply_effects(current, {}, [{"op": "quest_set", "id": "quest", "state": "completed"}],
                      scene=2, plot_ids={"x"})


def test_cycles_unresolved_nodes_and_forged_character_or_place_ids_are_rejected():
    raw = plan()
    raw["nodes"][1]["options"][1]["next_node"] = "opening"
    raw["nodes"][1]["options"][1]["ending"] = None
    with pytest.raises(ValueError, match="chronology"):
        validate_plan(raw)
    raw = plan()
    raw["nodes"][0]["speaker"] = "unknown_bystander"
    with pytest.raises(ValueError, match="backstory"):
        validate_plan(raw)
    raw = plan()
    raw["nodes"][1]["place"] = "place_without_lore"
    with pytest.raises(ValueError, match="lore"):
        validate_plan(raw)


def test_state_receipts_are_reproducible_and_no_output_is_live_game_mutation():
    compiled = validate_plan(plan())
    first = simulate(compiled, ["help_aria", "good_ending"])
    second = simulate(compiled, ["help_aria", "good_ending"])
    assert first == second
    assert first["story_quality_guaranteed"] is False
    assert all(len(s["receipt_digest"]) == 64 for s in first["steps"])
    assert first["receipt_digest"] != compiled["source_digest"]
    assert compiled["initial_state"]["quests"] == {}



def test_global_dialogue_history_ids_are_unique_across_rejoining_branches():
    story = plan()
    story["nodes"][1]["options"][0]["id"] = "help_aria"
    with pytest.raises(ValueError, match="globally unique"):
        validate_plan(story)


def test_surprises_require_prior_planted_plot_clues_and_can_then_be_paid_off():
    story = plan()
    story["nodes"][1]["options"][0]["effects"].insert(
        -1, threat("surprise", "truth"),
    )
    assert simulate(validate_plan(story), ["help_aria", "good_ending"])["ending_accepted"]
    story["nodes"][0]["options"][0]["effects"] = [
        e for e in story["nodes"][0]["options"][0]["effects"]
        if e.get("op") != "thread"
    ]
    with pytest.raises(ValueError, match="previously authored open clue"):
        simulate(validate_plan(story), ["help_aria", "good_ending"])


def test_ending_lore_requires_bounded_unique_knowledge_ids():
    story = plan()
    story["endings"][0]["required_lore"] = "this string must not be read as a list"
    with pytest.raises(ValueError, match="bounded list"):
        validate_plan(story)



def test_interlocking_city_person_faction_citizen_and_law_standings_unlock_options():
    state = initial_state()
    changes = [
        reputation("glass_city", 35, "city"),
        reputation("aria", 65, "person"),
        reputation("citizens", 30, "citizens"),
        reputation("council", 10, "government"),
        reputation("silver_gang", -50, "gang"),
        {"op": "meter_delta", "kind": "law_heat", "scope": "city",
         "subject": "city_watch", "delta": 25},
        {"op": "flag_set", "id": "council_invitation"},
    ]
    from core.branching_narrative import validate_effect
    current, threads, logs = apply_effects(
        state, {}, [validate_effect(e) for e in changes],
        scene=2, plot_ids={"recognized"},
    )
    guard = validate_condition({"op": "all", "items": [
        {"op": "meter", "kind": "reputation", "scope": "city",
         "subject": "glass_city", "comparison": "gte", "value": 30},
        {"op": "meter", "kind": "reputation", "scope": "person",
         "subject": "aria", "comparison": "gte", "value": 60},
        {"op": "meter", "kind": "reputation", "scope": "citizens",
         "subject": "citizens", "comparison": "gte", "value": 20},
        {"op": "meter", "kind": "reputation", "scope": "government",
         "subject": "council", "comparison": "gte", "value": 5},
        {"op": "meter", "kind": "reputation", "scope": "gang",
         "subject": "silver_gang", "comparison": "lte", "value": -40},
        {"op": "meter", "kind": "law_heat", "scope": "city",
         "subject": "city_watch", "comparison": "lte", "value": 30},
        {"op": "flag", "id": "council_invitation"},
    ]})
    assert holds(guard, current) is True
    current["meters"]["reputation:person:aria"] = -20
    assert holds(guard, current) is False


def test_legal_heat_demands_specific_law_fate_in_epilogue():
    story = plan()
    story["nodes"][0]["options"][0]["effects"].append({
        "op": "meter_delta", "kind": "law_heat", "scope": "city",
        "subject": "city_watch", "delta": 50,
    })
    compiled = validate_plan(story)
    result = simulate(compiled, ["help_aria", "good_ending"])
    assert result["ending_accepted"] is False
    assert result["unresolved_faction_conclusions"] == ["city_watch"]
    story["endings"][0]["faction_conclusions"]["city_watch"] = (
        "The city watch accepts the legal reforms and recalls the earlier conflict."
    )
    assert simulate(validate_plan(story), ["help_aria", "good_ending"])["ending_accepted"]



def test_unwoven_npc_and_place_lore_or_fabricated_relationships_fail_closed():
    story = plan()
    story["characters"][0]["relationships"] = ["missing_companion"]
    with pytest.raises(ValueError, match="non-existent relationship"):
        validate_plan(story)
    story = plan()
    story["places"][0]["discovered_by"] = ["unrecorded_character"]
    with pytest.raises(ValueError, match="unknown character"):
        validate_plan(story)
    story = plan()
    story["characters"][0]["plot_threads"].append("unwritten_sibling_mystery")
    with pytest.raises(ValueError, match="never woven"):
        validate_plan(story)
    story = plan()
    story["places"][0]["plot_threads"].append("missing_city_legend")
    with pytest.raises(ValueError, match="never woven"):
        validate_plan(story)



def test_same_nominal_good_ending_can_have_different_personal_and_city_epilogues():
    story = plan()
    second_approach = deepcopy(story["nodes"][0]["options"][0])
    second_approach["id"] = "help_aria_in_secret"
    second_approach["label"] = "Protect Aria secretly rather than openly."
    second_approach["dialogue"] = "Aria, trust me with the secret plan."
    second_approach["effects"].append({"op": "flag_set", "id": "secret_oath"})
    story["nodes"][0]["options"].append(second_approach)
    story["endings"][0]["variants"] = [{
        "id": "secret_oath_variation",
        "guard": {"op": "flag", "id": "secret_oath"},
        "overrides": {
            "epilogue": "Aria quietly keeps the charter hidden while the restored city remembers its unsung hero.",
            "character_conclusions": {
                "aria": "Aria chooses a private life, while guarding the council's secret accords.",
            },
            "place_conclusions": {
                "glass_city": "Glass City prospers publicly while its underground oath remains unknown.",
            },
        },
    }]
    compiled = validate_plan(story)
    public = simulate(compiled, ["help_aria", "good_ending"])
    secret = simulate(compiled, ["help_aria_in_secret", "good_ending"])
    assert public["ending_id"] == secret["ending_id"] == "restoration"
    assert public["ending_accepted"] and secret["ending_accepted"]
    assert public["ending_variants_selected"] == []
    assert secret["ending_variants_selected"] == ["secret_oath_variation"]
    assert public["ending"]["epilogue"] != secret["ending"]["epilogue"]
    assert public["ending"]["character_conclusions"]["aria"] != (
        secret["ending"]["character_conclusions"]["aria"])
    assert public["receipt_digest"] != secret["receipt_digest"]
    audit = audit_outcomes(compiled, max_paths=100)
    assert audit["all_paths_verified"] is True


def test_conflicting_conditional_epilogues_are_rejected_not_silently_overwritten():
    story = plan()
    story["endings"][0]["variants"] = [
        {"id": "first", "guard": {"op": "always"}, "overrides": {
            "epilogue": "First rule claims the city enjoyed everlasting peace despite the suffering.",
        }},
        {"id": "second", "guard": {"op": "always"}, "overrides": {
            "epilogue": "Second rule claims that the entire city instead collapsed into disorder.",
        }},
    ]
    compiled = validate_plan(story)
    with pytest.raises(ValueError, match="Conflicting conditional ending"):
        simulate(compiled, ["help_aria", "good_ending"])
    audit = audit_outcomes(compiled, max_paths=100)
    assert audit["all_paths_verified"] is False
    assert audit["issue_count"] > 0


def test_variant_conditions_cannot_redefine_an_unknown_character_or_place():
    for field in ("character_conclusions", "place_conclusions"):
        story = plan()
        story["endings"][0]["variants"] = [{
            "id": "bad_fate",
            "guard": {"op": "always"},
            "overrides": {field: {"fictional_actor": "An invented fate."}},
        }]
        with pytest.raises(ValueError, match="unknown"):
            validate_plan(story)
