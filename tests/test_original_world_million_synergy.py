"""Cross-layer authored-domain × mechanical genre × continuation risk tests."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from skeleton.game.generation.original_foundation_compiler import (
    ROOTS, REGIME_COUNT,
)
from skeleton.game.generation.original_world_million_compiler import advanced_for
from skeleton.game.generation.original_world_million_runtime import (
    AdvancedAction, create_advanced, step_advanced, validate_game,
)
from skeleton.game.generation.original_world_million_synergy import (
    ARC_PRESSURE_CONSEQUENCE, DOMAIN_PRESSURE, FORM_ORDER,
    evaluate_pressure,
)


def state_for(domain: str, form: str = "platform", arc: str = "chapters"):
    root_i = next(i for i, r in enumerate(ROOTS) if r.domain == domain)
    return create_advanced(
        advanced_for(root_i * REGIME_COUNT, form, arc).advanced_id
    )


def turns(state, count):
    for _ in range(count):
        state, receipt = step_advanced(state, AdvancedAction("causal", "end_turn"))
        validate_game(state)
    return state


def test_160_explicit_domain_genre_intersections_have_real_constraints() -> None:
    assert len(DOMAIN_PRESSURE) == 16
    assert len(FORM_ORDER) == 10
    assert sum(len(values) for values in DOMAIN_PRESSURE.values()) == 160
    assert len(ARC_PRESSURE_CONSEQUENCE) == 12
    assert all(len(row) == 10 for row in DOMAIN_PRESSURE.values())
    assert set(FORM_ORDER) == {
        "platform", "puzzle", "tactics", "survival", "colony", "racing",
        "stealth", "commerce", "exploration", "rhythm",
    }


def test_same_genre_stress_changes_real_gameplay_differently_by_world_domain() -> None:
    civic = state_for("governance")
    material = state_for("materials")
    civic = replace(civic, mode=replace(civic.mode, damage=8))
    material = replace(material, mode=replace(material.mode, damage=8))
    civic = turns(civic, 4)
    material = turns(material, 4)
    assert civic.causal.duty == 0
    assert material.causal.duty > civic.causal.duty
    assert civic.mode.damage == material.mode.damage == 8
    assert civic.arc.checkpoint == material.arc.checkpoint == 4


def test_same_domain_genre_pressure_has_distinct_arc_costs() -> None:
    chapters = replace(
        state_for("materials", arc="chapters"),
        mode=replace(state_for("materials", arc="chapters").mode, damage=8),
    )
    mystery = replace(
        state_for("materials", arc="mystery"),
        mode=replace(state_for("materials", arc="mystery").mode, damage=8),
    )
    chapters = turns(chapters, 4)
    mystery = turns(mystery, 4)
    assert chapters.causal.duty >= 1
    assert mystery.arc.uncertainty >= 1
    assert mystery.causal.duty == 0
    assert chapters.arc.uncertainty == 0


def test_high_stress_triggers_only_at_a_real_progression_checkpoint() -> None:
    before = evaluate_pressure("materials", "platform", "chapters", 8, 3, 4)
    after = evaluate_pressure("materials", "platform", "chapters", 8, 4, 4)
    assert before.score == after.score == 5
    assert not before.triggered
    assert after.triggered and after.consequence == "duty"
    assert after.amount > 0


def test_low_stress_protects_player_against_automatic_punishment() -> None:
    result = evaluate_pressure("governance", "platform", "chapters", 0, 4, 4)
    assert result.score == 0
    assert not result.triggered
    assert result.amount == 0


def test_all_1920_domain_form_arc_combinations_have_defined_pressures() -> None:
    effects = set()
    for domain in DOMAIN_PRESSURE:
        for form in FORM_ORDER:
            for arc in ARC_PRESSURE_CONSEQUENCE:
                result = evaluate_pressure(domain, form, arc, 12, 12, 4)
                assert result.score >= 3
                assert result.explanation
                assert result.consequence in {
                    "duty", "hazard", "legacy", "outstanding", "trust",
                    "reserve", "uncertainty", "warmth", "civic",
                }
                effects.add((domain, form, arc))
    assert len(effects) == 16 * 10 * 12


@pytest.mark.parametrize("bad", [
    ("missing", "platform", "chapters", 0, 4, 4),
    ("geometry", "no-player-mode", "chapters", 0, 4, 4),
    ("geometry", "platform", "unsupported", 0, 4, 4),
    ("geometry", "platform", "chapters", -1, 4, 4),
    ("geometry", "platform", "chapters", True, 4, 4),
    ("geometry", "platform", "chapters", 0, 4, 0),
])
def test_unsafe_cross_layer_inputs_fail_closed(bad) -> None:
    with pytest.raises(ValueError):
        evaluate_pressure(*bad)
