"""Executable quest evidence for genre/progression/world-law configurations."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_world_million_compiler import (
    advanced_for, advanced_at,
)
from skeleton.game.generation.original_world_million_runtime import (
    AdvancedAction, create_advanced, step_advanced,
)
from skeleton.game.generation.original_world_million_objectives import (
    STAGES, objectives, objective_report, guided_next_action,
)
from skeleton.game.generation.original_world_play_forms import (
    PLAY_FORMS, PROGRESSION_LAWS,
)
from skeleton.game.generation.original_world_million_cli import main


def run(state, layer, verb, amount=1, target=-1, option=""):
    return step_advanced(state, AdvancedAction(layer, verb, amount, target, option))[0]


def test_each_of_120_genre_arc_pairings_has_actual_goal_proofs() -> None:
    for form in PLAY_FORMS:
        for arc in PROGRESSION_LAWS:
            state = create_advanced(
                advanced_for(0, form.form_id, arc.arc_id).advanced_id
            )
            progress = objectives(state)
            assert len(progress) == len(STAGES) == 5
            assert tuple(x.goal_id for x in progress) == STAGES
            assert progress[0].unlocked
            assert not progress[0].verified
            assert all(not goal.verified for goal in progress)
            assert all(goal.explanation and goal.causal_proof for goal in progress)
            report = objective_report(state)
            assert report["completed_objectives"] == 0
            assert report["not_a_native_game_certification"]
            assert "Play one" in guided_next_action(state)


def test_puzzle_completion_enables_branching_afterlife_without_forcing_global_win() -> None:
    state = create_advanced(advanced_for(0, "puzzle", "branching").advanced_id)
    state = run(state, "mode", "toggle", target=0)
    state = run(state, "mode", "toggle", target=2)
    state = run(state, "mode", "pass")
    goals = objectives(state)
    assert goals[0].verified
    assert goals[2].verified
    assert not goals[3].verified
    state = run(state, "arc", "choose", option="care")
    goals = objectives(state)
    assert goals[3].verified
    # The branch affects future turns and may be played after a local win.
    state = run(state, "causal", "end_turn")
    assert state.mode.cleared
    assert objective_report(state)["continuation"] == "branching"


def test_unwinnable_continuations_have_playable_objectives_not_fake_victory() -> None:
    for policy in ("endless", "rescue"):
        game = create_advanced(advanced_for(0, "puzzle", policy).advanced_id)
        game = run(game, "mode", "toggle", target=0)
        game = run(game, "mode", "toggle", target=2)
        game = run(game, "mode", "pass")
        assert game.mode.cleared
        for _ in range(6):
            game = run(game, "causal", "end_turn")
        report = objective_report(game)
        assert report["world_winnable"] is False
        assert report["chapter_completed"] is True
        assert report["arc_completed"] is False
        assert report["objectives"][2]["verified"]
        game = run(game, "mode", "toggle", target=0)
        assert game.events > 9


def test_root_unwinnable_policy_is_not_overridden_by_arc_victory_policy() -> None:
    # A single authored root can intentionally prohibit a final victory.
    from skeleton.game.generation.original_foundation_compiler import (
        ROOTS, REGIME_COUNT,
    )
    i = next(n * REGIME_COUNT for n, root in enumerate(ROOTS)
             if root.ending_policy == "unwinnable")
    state = create_advanced(advanced_for(i, "puzzle", "chapters").advanced_id)
    assert objective_report(state)["world_winnable"] is False


def test_objective_director_is_read_only_and_deterministic() -> None:
    state = create_advanced(advanced_at(1_228_799).advanced_id)
    first = objective_report(state)
    second = objective_report(state)
    assert first == second
    assert len(first["objectives"]) == 5
    assert first["world_id"] == "adv-1228799"


def test_mystery_false_conclusion_has_consequence_and_corrected_proof() -> None:
    state = create_advanced(advanced_for(0, "puzzle", "mystery").advanced_id)
    state = run(state, "arc", "commit")
    assert state.arc.uncertainty == 1
    assert state.arc.chapter == 0
    state = run(state, "causal", "study", amount=2)
    state = run(state, "arc", "investigate", amount=3)
    state = run(state, "arc", "commit")
    report = objective_report(state)
    assert report["objectives"][3]["verified"]
    assert state.arc.uncertainty > 0


def test_seasonal_objective_does_not_uncomplete_on_yearly_wrap() -> None:
    state = create_advanced(advanced_for(0, "survival", "seasonal").advanced_id)
    for _ in range(16):
        state = run(state, "causal", "end_turn")
    assert state.arc.season == 0
    assert state.arc.checkpoint == 16
    assert objectives(state)[3].verified


def test_goalbook_in_offline_cli_after_real_puzzle_actions(capsys) -> None:
    script = '[{"layer":"mode","verb":"toggle","target":0},' \
             '{"layer":"mode","verb":"toggle","target":2},' \
             '{"layer":"mode","verb":"pass"}]'
    assert main([
        "--base", "0", "--form", "puzzle", "--arc", "endless",
        "--actions-json", script, "--objectives",
    ]) == 0
    printed = json.loads(capsys.readouterr().out)
    report = printed["objectives"]
    assert report["chapter_completed"]
    assert not report["world_winnable"]
    assert report["completed_objectives"] >= 2
    assert "next_action" in printed
