"""Model gameplay proposals become bounded data consumed by executable rules."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json

import pytest

from skeleton.forge.ai_builder import ModelPlanner, grant_providers
from skeleton.forge.ai_builder.plan_guard import guard_proposal
from skeleton.forge.ai_builder.plan_schema import (
    GAMEPLAY_RESPONSE_SCHEMA, PlanParseError, parse_model_plan,
)
from skeleton.forge.game_content import generate_content
from skeleton.forge.game_design_spec import (
    GAMEPLAY_FIELDS, GOLDEN_BRIEFS, GameplayValidationError,
    compile_brief, default_gameplay, gameplay_constraints, gameplay_for_spec, validate_gameplay,
)
from skeleton.forge.genre_project import execute_core_loop, loop_succeeded


@pytest.mark.parametrize("brief", GOLDEN_BRIEFS)
def test_brief_defaults_and_legacy_v1_spec_remain_supported(brief):
    spec = compile_brief(brief["brief"])
    assert spec["gameplay"] == default_gameplay(brief["genre"])
    assert set(spec["gameplay"]) == GAMEPLAY_FIELDS
    legacy = {k: v for k, v in spec.items() if k != "gameplay"}
    assert gameplay_for_spec(legacy) == spec["gameplay"]
    assert compile_brief(brief["brief"]) == spec


def test_explicit_brief_labels_compile_to_bounded_data_without_changing_game_identity():
    spec = compile_brief(
        "A small platformer. Difficulty: hard. Theme: neon. "
        "Objective: Activate the northern relay. Player speed: 300. Encounter style: ranged."
    )
    assert spec["gameplay"] == {
        "difficulty": "hard", "theme": "neon", "objective_label": "Activate the northern relay",
        "player_speed": 300, "encounter_style": "ranged",
    }
    assert spec["genre"] == "platformer"
    assert spec["engine"] == "godot4" and spec["scope"] == "small"


@pytest.mark.parametrize("label", [
    "Difficulty: impossible.", "Theme: http://untrusted.example.",
    "Encounter style: execute.", "Player speed: true.", "Player speed: 300.5.",
    "Player speed: 9999999999999999.", "Player speed: 119.", "Player speed: 361.",
])
def test_invalid_explicit_labels_fail_instead_of_coercing_or_ignoring(label):
    with pytest.raises(GameplayValidationError):
        compile_brief("A small shooter. " + label)


@pytest.mark.parametrize("speed", [True, False, None, "230", 230.0, float("nan"),
                                  float("inf"), -1, 119, 361, 10**100])
def test_gameplay_denies_boolean_float_nonfinite_and_out_of_range_speed(speed):
    proposal = default_gameplay()
    proposal["player_speed"] = speed
    with pytest.raises(GameplayValidationError) as error:
        validate_gameplay(proposal)
    assert "invalid:gameplay.player_speed" in error.value.violations


@pytest.mark.parametrize("field,value", [
    ("difficulty", "expert"), ("difficulty", True), ("theme", None), ("theme", "remote"),
    ("encounter_style", "../../execute"), ("objective_label", ""),
    ("objective_label", "   "), ("objective_label", "x" * 101),
    ("objective_label", "two\nlines"), ("objective_label", "binary\x00text"),
    ("objective_label", "\ud800"), ("objective_label", 5),
])
def test_gameplay_closed_field_validation(field, value):
    proposal = default_gameplay()
    proposal[field] = value
    with pytest.raises(GameplayValidationError):
        validate_gameplay(proposal)


def test_gameplay_unknown_missing_and_nonobject_fields_are_rejected_atomically():
    for raw in [None, [], "normal", {}, {"difficulty": "easy"},
                {**default_gameplay(), "script": "quit()"},
                {**default_gameplay(), "path": "/tmp/escape"},
                {**default_gameplay(), "provider": "remote"}]:
        with pytest.raises(GameplayValidationError):
            validate_gameplay(raw)
    original = default_gameplay()
    copied = validate_gameplay(original)
    copied["theme"] = "neon"
    assert original["theme"] == "moss"


def test_valid_unicode_objective_and_speed_boundaries():
    for speed in (120, 360):
        gameplay = {**default_gameplay(), "player_speed": speed,
                    "objective_label": "灯台を守る 🌱"}
        assert validate_gameplay(gameplay) == gameplay


def test_explicit_gameplay_constraints_keep_user_authority_over_valid_model_enrichment():
    spec = compile_brief("A shooter. Difficulty: hard. Theme: frost. Objective: Protect the beacon.")
    assert gameplay_constraints(spec["brief"]) == {
        "difficulty": "hard", "theme": "frost", "objective_label": "Protect the beacon",
    }
    proposed = {**spec["gameplay"], "difficulty": "easy", "theme": "ember"}
    rejected, violations = guard_proposal(spec, {"gameplay": proposed})
    assert rejected == spec
    assert set(violations) == {"constraints:gameplay.difficulty", "constraints:gameplay.theme"}
    enriched, violations = guard_proposal(spec, {"gameplay": {
        **spec["gameplay"], "encounter_style": "ranged", "player_speed": 300,
    }})
    assert not violations
    assert enriched["gameplay"]["encounter_style"] == "ranged"
    assert enriched["gameplay"]["difficulty"] == "hard"


def test_conflicting_duplicate_brief_constraints_fail_instead_of_choosing_for_user():
    with pytest.raises(GameplayValidationError):
        compile_brief("A shooter. Difficulty: hard. Difficulty: easy.")


def test_plan_guard_admits_gameplay_with_locked_constraints_and_exact_hash():
    compiled = compile_brief("A small shooter. Scope: small prototype.")
    proposed = {**default_gameplay(), "difficulty": "hard", "encounter_style": "swarm"}
    accepted, violations = guard_proposal(compiled, {"gameplay": proposed, "genre": "rpg_roguelike",
                                                   "engine": "shell", "scope": "large", "brief": "replace"})
    assert accepted["gameplay"] == proposed
    for key in ("genre", "engine", "scope", "brief"):
        assert accepted[key] == compiled[key]
        assert "locked:" + key in violations
    assert accepted["spec_id"] != compiled["spec_id"]
    assert guard_proposal(accepted, {})[0] == accepted
    bad = {**proposed, "player_speed": True, "script": "process.run()"}
    rejected, violations = guard_proposal(compiled, {"gameplay": bad})
    assert rejected == compiled
    assert "invalid:gameplay.player_speed" in violations and "unknown:gameplay" in violations


@pytest.mark.parametrize("text", [
    '{"gameplay":{"player_speed":NaN}}',
    '{"gameplay":{"difficulty":"easy","difficulty":"hard"}}',
    '{"title":"first","title":"second"}',
    '{"title":"' + "x" * (33 * 1024) + '"}',
])
def test_model_json_duplicate_nonfinite_or_oversized_output_is_not_laundered(text):
    with pytest.raises(PlanParseError):
        parse_model_plan(text)


def test_model_plan_unreadable_unicode_and_nonfinite_mappings_are_rejected():
    for raw in ['{"title":"\ud800"}', {"title": "\ud800"},
                {"gameplay": {"player_speed": float("nan")}},
                {"gameplay": {"player_speed": float("inf")}}]:
        with pytest.raises(PlanParseError):
            parse_model_plan(raw)


def test_model_request_asks_for_closed_gameplay_and_keeps_router_authority():
    from tests.forge_ai_builder.fakes import FakeRouter, gate_and_issuer
    gate, issuer = gate_and_issuer()
    gameplay = {**default_gameplay("platformer"), "theme": "frost", "difficulty": "easy"}
    router = FakeRouter(reply=lambda _: json.dumps({"gameplay": gameplay}))
    outcome = asyncio.run(ModelPlanner(router, gate=gate, cap=grant_providers(issuer, ["alpha"]))
                          .plan("A small platformer."))
    assert outcome.used_model and outcome.spec["gameplay"] == gameplay
    assert outcome.spec["genre"] == "platformer" and not outcome.violations
    request = router.requests[0]
    assert request.response_schema["properties"]["gameplay"] == GAMEPLAY_RESPONSE_SCHEMA
    assert GAMEPLAY_RESPONSE_SCHEMA["additionalProperties"] is False
    assert set(GAMEPLAY_RESPONSE_SCHEMA["required"]) == GAMEPLAY_FIELDS
    assert "gameplay" in request.messages[0].content
    assert "providers" in request.messages[0].content


@pytest.mark.parametrize("difficulty", ["easy", "normal", "hard"])
@pytest.mark.parametrize("style", ["swarm", "patrol", "ranged"])
@pytest.mark.parametrize("brief", GOLDEN_BRIEFS)
def test_gameplay_changes_real_content_and_every_small_core_loop_is_winnable(tmp_path, difficulty, style, brief):
    spec = compile_brief(brief["brief"])
    spec, violations = guard_proposal(spec, {"gameplay": {
        **spec["gameplay"], "difficulty": difficulty, "encounter_style": style,
    }})
    assert not violations
    content = generate_content(spec, root=tmp_path)
    assert content["gameplay"] == spec["gameplay"]
    assert all(row["style"] == style for row in content["encounters"])
    assert len({row["role"] for row in content["encounters"]}) == 3
    assert len({row["hp"] for row in content["encounters"]}) == len(content["encounters"])
    assert content["encounters"][-1]["loot"] > content["encounters"][0]["loot"]
    assert content["economy"]["closing_balance"] == (
        content["economy"]["starting_balance"]
        + sum(row["loot"] for row in content["encounters"])
        - content["economy"]["sink_cost"]
    )
    assert loop_succeeded(execute_core_loop(content, spec["genre"]))


def test_difficulty_and_style_change_combat_risk_rewards_and_platform_challenge(tmp_path):
    compiled = compile_brief("A large shooter campaign.")
    bundles = {}
    for difficulty in ("easy", "normal", "hard"):
        spec = deepcopy(compiled)
        spec["gameplay"]["difficulty"] = difficulty
        bundles[difficulty] = generate_content(spec, root=tmp_path / difficulty)
    assert bundles["easy"]["encounters"][0]["hp"] < bundles["normal"]["encounters"][0]["hp"] < bundles["hard"]["encounters"][0]["hp"]
    assert bundles["easy"]["economy"]["closing_balance"] < bundles["normal"]["economy"]["closing_balance"] < bundles["hard"]["economy"]["closing_balance"]
    for bundle in bundles.values():
        assert loop_succeeded(execute_core_loop(bundle, "top_down_shooter"))
    spec = deepcopy(compiled)
    spec["gameplay"]["difficulty"] = "hard"
    spec["gameplay"]["encounter_style"] = "ranged"
    hard_ranged = generate_content(spec, root=tmp_path / "ranged")
    assert loop_succeeded(execute_core_loop(hard_ranged, "top_down_shooter"))
    assert hard_ranged["encounters"] != bundles["hard"]["encounters"]
    easy = compile_brief("A platformer. Difficulty: easy.")
    hard = compile_brief("A platformer. Difficulty: hard.")
    easy_content = generate_content(easy, root=tmp_path / "platform-easy")
    hard_content = generate_content(hard, root=tmp_path / "platform-hard")
    assert hard_content["goal_x"] > easy_content["goal_x"]
    assert all(row["gap"] <= hard_content["jump_reach"] for row in hard_content["platforms"])


def test_content_rejects_invalid_gameplay_before_generating_artifacts(tmp_path):
    spec = compile_brief("A small shooter.")
    spec["gameplay"]["player_speed"] = float("nan")
    with pytest.raises(GameplayValidationError):
        generate_content(spec, root=tmp_path)
    assert not list(tmp_path.iterdir())
