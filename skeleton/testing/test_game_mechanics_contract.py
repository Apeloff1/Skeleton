import math

import pytest

from skeleton.game import (
    AIBehaviorSpec,
    CombatStyle,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsError,
    GameMechanicsGenerator,
    MechanicType,
    ProgressionStyle,
    ProgressionSystemSpec,
)


def test_real_time_combat_uses_real_time_template_not_turn_based_fallback():
    system = GameMechanicsGenerator.generate_combat_system(
        CombatSystemSpec(style=CombatStyle.REAL_TIME)
    )

    assert system["style"] == "real_time"
    assert system["core_mechanics"]["structure"] == "continuous"
    assert system["core_mechanics"]["cooldown_based"] is True
    assert "actions_per_turn" not in system["core_mechanics"]
    assert system["magic_system"]["casting_time"] is False


def test_tactical_combat_keeps_grid_specific_contract():
    system = GameMechanicsGenerator.generate_combat_system(
        CombatSystemSpec(
            style="tactical",
            include_magic=False,
            include_status_effects=False,
            party_based=True,
            enemy_ai_complexity="complex",
        )
    )

    assert system["core_mechanics"]["structure"] == "grid_based"
    assert system["damage_types"] == ["physical"]
    assert system["status_effects"] == []
    assert "magic_system" not in system
    assert system["party_mechanics"]["switch_cost"] == 0.5
    assert system["enemy_ai"]["learning_enabled"] is True


def test_exponential_progression_total_xp_accumulates_actual_curve():
    progression = GameMechanicsGenerator.generate_progression_system(
        ProgressionSystemSpec(
            style=ProgressionStyle.EXPONENTIAL,
            max_level=3,
            skill_tree_branches=0,
        )
    )

    rows = progression["xp_table"]
    assert [row["xp_required"] for row in rows] == [150, 225, 337]
    assert [row["total_xp"] for row in rows] == [150, 375, 712]
    assert progression["skill_tree"] is None


def test_skill_tree_and_prestige_are_bounded_explicit_outputs():
    progression = GameMechanicsGenerator.generate_progression_system(
        ProgressionSystemSpec(
            style=ProgressionStyle.SKILL_TREE,
            max_level=10,
            include_prestige=True,
            skill_tree_branches=2,
        )
    )

    branches = progression["skill_tree"]["branches"]
    assert [branch["name"] for branch in branches] == ["Combat", "Magic"]
    assert branches[0]["nodes"][1]["prerequisites"] == ["skill_0_0"]
    assert progression["prestige"]["unlock_level"] == 10


def test_ai_behavior_order_is_stable_and_custom_duplicates_are_removed():
    spec = AIBehaviorSpec(
        entity_type="guard",
        behaviors=("patrol", "raise_alarm", "raise_alarm"),
        aggression_level=0.5,
        intelligence_level=0.5,
    )

    first = GameMechanicsGenerator.generate_ai_behavior(spec)
    second = GameMechanicsGenerator.generate_ai_behavior(spec)
    first_names = [node["name"] for node in first["root"]["children"]]
    second_names = [node["name"] for node in second["root"]["children"]]

    assert first_names == second_names
    assert first_names == [
        "patrol",
        "investigate_noise",
        "attack_if_threatened",
        "seek_advantage",
        "retreat_when_hurt",
        "raise_alarm",
    ]


def test_description_parser_returns_typed_mechanic_and_style_hints():
    parsed = GameMechanicsGenerator.parse_mechanic_description(
        "Build a real-time survival RPG with combat, crafting, shops, and enemy AI."
    )

    assert parsed["combat_style"] == CombatStyle.REAL_TIME
    assert MechanicType.COMBAT in parsed["mechanic_types"]
    assert MechanicType.CRAFTING in parsed["mechanic_types"]
    assert MechanicType.ECONOMY in parsed["mechanic_types"]
    assert MechanicType.AI_BEHAVIOR in parsed["mechanic_types"]
    assert "rpg" in parsed["genre_hints"]
    assert "survival" in parsed["genre_hints"]


def test_economy_inputs_are_validated_before_symbol_generation():
    with pytest.raises(GameMechanicsError):
        EconomySystemSpec(currencies=("",))

    with pytest.raises(GameMechanicsError):
        EconomySystemSpec(currencies=("gold", "gold"))

    economy = GameMechanicsGenerator.generate_economy_system(
        EconomySystemSpec(
            currencies=("gold", "gems"),
            include_crafting=True,
            inflation_model=True,
        )
    )
    assert economy["currencies"]["gold"]["symbol"] == "G"
    assert economy["crafting"] is not None
    assert economy["inflation"]["enabled"] is True


def test_resource_bounds_and_non_finite_ai_levels_fail_closed():
    with pytest.raises(GameMechanicsError):
        ProgressionSystemSpec(style="linear", max_level=1001)

    with pytest.raises(GameMechanicsError):
        AIBehaviorSpec(entity_type="npc", aggression_level=math.nan)

    with pytest.raises(GameMechanicsError):
        GameMechanicsGenerator.parse_mechanic_description("x" * 8001)
