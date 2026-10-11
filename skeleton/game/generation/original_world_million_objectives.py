"""Objective director: causal root × genre × continuation play structures.

These are executable, read-only milestone evaluations derived from the game
state. Nothing is awarded for merely creating a million indexed blueprints.
Quest conditions are proofs about actual actions, finite resources and
continuing consequences; nonwinnable worlds never receive fake global wins.
"""
from __future__ import annotations

from dataclasses import dataclass

from .original_foundation_compiler import FoundationError
from .original_world_million_runtime import (
    AdvancedState, validate_game,
)

STAGES = ("understand", "intervene", "practice", "continue", "aftermath")


@dataclass(frozen=True)
class Objective:
    goal_id: str
    title: str
    explanation: str
    verified: bool
    current: int
    required: int
    unlocked: bool
    continuation: str
    causal_proof: str

    def as_dict(self) -> dict:
        return {
            "id": self.goal_id,
            "title": self.title,
            "explanation": self.explanation,
            "verified": self.verified,
            "current": self.current,
            "required": self.required,
            "unlocked": self.unlocked,
            "continuation": self.continuation,
            "causal_proof": self.causal_proof,
        }


def _genre_progress(state: AdvancedState, form: str) -> tuple[int, int, str]:
    m = state.mode
    progress = {
        "platform": (m.course, 12, "platforms reached without exhausting protection"),
        "puzzle": (m.gates, 1, "a precisely verified logic gate unlocked"),
        "tactics": (8 - m.enemy, 8, "enemy defenses reduced through bounded battle or parley"),
        "survival": (min(state.causal.tick, 6), 6, "survived scarce world turns"),
        "colony": (m.population, 3, "residents housed and fed in persistent settlement"),
        "racing": (m.laps, 1, "legal completed track laps"),
        "stealth": (m.course, 10, "low-alert movement across watched rooms"),
        "commerce": (m.wallet, 14, "finite counterpart market transactions"),
        "exploration": (len(m.revealed), 6, "separately reached and discovered sectors"),
        "rhythm": (m.combo, 4, "consecutive notes aligned to the changing beat"),
    }
    return progress[form]


def _arc_progress(state: AdvancedState, arc_id: str) -> tuple[int, int, str]:
    a = state.arc
    values = {
        "chapters": (a.chapter, 1, "complete a played chapter with recognized objective"),
        "endless": (state.causal.tick, 6, "sustain a world across a cycle with no final win"),
        "roguelite": (a.attempts, 1, "complete or reset a real expedition run"),
        "dynasty": (a.generation, 1, "transfer duties to the next generation"),
        "factions": (int(bool(a.branch)), 1, "make a binding faction commitment"),
        "sandbox": (a.civic, 1, "invest actual material in self-chosen development"),
        "mystery": (a.chapter, 1, "test a theory using three expended independent clues"),
        "seasonal": (a.season, 1, "reach a changed seasonal regime"),
        "rescue": (a.rescues, 1, "deliver finite aid to a remote need"),
        "campaign": (a.territory, 1, "take an accounted region after a played objective"),
        "civilization": (a.civic, 1, "make concrete long-term public investment"),
        "branching": (int(bool(a.branch)), 1, "make an irreversible narrative choice"),
    }
    return values[arc_id]


def objectives(state: AdvancedState) -> tuple[Objective, ...]:
    law = validate_game(state)
    world, mode, arc = state.causal, state.mode, state.arc
    genre, continuation = law.mode.form.form_id, law.arc.arc_id
    genre_now, genre_required, genre_proof = _genre_progress(state, genre)
    arc_now, arc_required, arc_proof = _arc_progress(state, continuation)
    initial = Objective(
        "understand",
        "Read the original world's causal obligations",
        law.mode.base.root.invariant + " " + law.mode.base.regime.invariant,
        mode.actions > 0 or world.event_count > 0,
        int(mode.actions > 0 or world.event_count > 0), 1,
        True,
        "tutorial",
        "The player has actually submitted at least one legal world or genre action",
    )
    intervention = Objective(
        "intervene",
        f"Test {law.mode.base.root.title}'s causal law",
        law.mode.base.coupling + " " + law.mode.base.player_lever,
        world.primary > 0,
        min(1, world.primary), 1,
        initial.verified,
        law.mode.base.ending_policy,
        "A legal causal intervention changed the source-world progress meter",
    )
    practice = Objective(
        "practice",
        f"Play {law.mode.form.title} to a real milestone",
        law.mode.form.player_loop + ". " + law.mode.form.win_criterion,
        mode.cleared,
        min(genre_now, genre_required), genre_required,
        initial.verified,
        law.arc.continuation_policy,
        genre_proof,
    )
    continue_goal = Objective(
        "continue",
        f"Develop {law.arc.title} after the opening actions",
        law.arc.causal_contract + " " + law.arc.player_agency,
        arc_now >= arc_required,
        min(arc_now, arc_required), arc_required,
        initial.verified and (practice.verified or intervention.verified),
        law.arc.continuation_policy,
        arc_proof,
    )
    # Closure is conditional and never forced upon explicitly open worlds.
    allows_closure = law.arc.continuation_policy not in (
        "open", "persistent", "unwinnable", "looping",
    )
    aftermath_achieved = (
        practice.verified and continue_goal.verified and
        (arc.completed if allows_closure else world.tick >= 2)
    )
    aftermath = Objective(
        "aftermath",
        "Maintain a world beyond the first objective",
        law.arc.setback_law + " " + law.mode.base.failure_pressure,
        aftermath_achieved,
        int(aftermath_achieved), 1,
        practice.verified and continue_goal.verified,
        law.arc.continuation_policy,
        "Either a real postgame epilogue or two additional world turns "
        "without asserting a final victory for intentionally open worlds",
    )
    return (initial, intervention, practice, continue_goal, aftermath)


def objective_report(state: AdvancedState) -> dict:
    law = validate_game(state)
    goalbook = objectives(state)
    return {
        "version": "original-million-objective-director.v1",
        "world_id": law.advanced_id,
        "source": law.mode.base.foundation_id,
        "play_form": law.mode.form.form_id,
        "continuation": law.arc.arc_id,
        "chapter_completed": state.mode.cleared,
        "arc_completed": state.arc.completed,
        "world_winnable": law.arc.continuation_policy != "unwinnable",
        "not_a_native_game_certification": True,
        "objectives": [x.as_dict() for x in goalbook],
        "completed_objectives": sum(x.verified for x in goalbook),
        "visible_objectives": sum(x.unlocked for x in goalbook),
    }


def guided_next_action(state: AdvancedState) -> str:
    """Choose a truthful actionable suggestion, never execute it automatically."""
    law = validate_game(state)
    for task in objectives(state):
        if task.verified or not task.unlocked:
            continue
        if task.goal_id == "understand":
            return "Play one supported mode command or a causal study action"
        if task.goal_id == "intervene":
            return "Use causal intervene, gathering supplies, energy and consent first"
        if task.goal_id == "practice":
            return "Advance the three authored mechanics for " + law.mode.form.title
        if task.goal_id == "continue":
            return "Use arc actions or world turns under the " + law.arc.title + " contract"
        if task.goal_id == "aftermath":
            return "Continue playing after the chapter milestone and manage remaining obligations"
    return "All currently tracked milestones are met; world simulation can continue"
