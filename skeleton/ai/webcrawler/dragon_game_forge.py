"""Game Forge: evidence-to-prototype orchestration for the dragon companion.

This module builds *original* game design specifications from confirmed
mechanics preferences, runs deterministic offline evaluation against
user-selected constraints, and compares two competing proposals. It does
not pretend to generate executable games or infer user preference from
unconfirmed gameplay observations.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Iterable

from .dragon_game_mechanics import GameTasteProfile, Mechanic


@dataclass(frozen=True)
class ForgePolicy:
    max_candidates: int = 100
    max_iterations: int = 10000
    max_mechanics: int = 12
    minimum_confidence: float = 0.6
    require_confirmed_taste: bool = True


@dataclass(frozen=True)
class GameDesignConstraint:
    genre: str
    target_platform: str
    accessibility: tuple[str, ...] = ()
    originality_notes: tuple[str, ...] = ()
    max_complexity: int = 8


@dataclass(frozen=True)
class GameMechanicDesign:
    mechanic: Mechanic
    objective: str
    player_action: str
    system_response: str
    feedback: str
    validation: str


@dataclass(frozen=True)
class GamePrototypeSpec:
    candidate_id: str
    title: str
    design_goal: str
    mechanics: tuple[GameMechanicDesign, ...]
    constraints: GameDesignConstraint
    source_taste_fingerprint: str
    original_assets_required: bool = True


@dataclass(frozen=True)
class ForgeEvaluation:
    candidate_id: str
    taste_alignment: float
    coverage: float
    accessibility: float
    complexity: float
    total: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ForgeCompetition:
    winner: GamePrototypeSpec
    runner_up: GamePrototypeSpec
    winner_score: ForgeEvaluation
    runner_up_score: ForgeEvaluation
    rounds: int
    fingerprint: str


_MECHANICS: dict[Mechanic, tuple[str, str, str, str]] = {
    Mechanic.MOVEMENT: ("Traverse readable spaces", "Adjust direction and speed", "Apply tunable acceleration", "Clear motion and stopping cues"),
    Mechanic.CAMERA: ("Preserve spatial awareness", "Control view orientation", "Track focus without obscuring action", "Smooth camera feedback"),
    Mechanic.COMBAT: ("Reward deliberate timing", "Select and time an action", "Resolve telegraphed interactions", "Distinct hit and recovery cues"),
    Mechanic.PUZZLE: ("Encourage experimentation", "Manipulate readable elements", "Update a consistent rule system", "Immediate causal feedback"),
    Mechanic.EXPLORATION: ("Reward curiosity", "Inspect and traverse landmarks", "Reveal optional discoveries", "Discoverable visual and audio cues"),
    Mechanic.CRAFTING: ("Make resources meaningful", "Combine known components", "Apply explicit recipes and costs", "Preview outcome before commitment"),
    Mechanic.BUILDING: ("Support expressive construction", "Place and adjust structures", "Validate stability and placement", "Readable placement previews"),
    Mechanic.DIALOGUE: ("Support meaningful choices", "Choose contextual responses", "Track consequences consistently", "Visible character reactions"),
    Mechanic.STEALTH: ("Enable deliberate avoidance", "Control visibility and noise", "Update observable detection state", "Legible detection indicators"),
    Mechanic.PLATFORMING: ("Reward precise traversal", "Jump and adjust trajectory", "Apply consistent collision rules", "Responsive takeoff and landing"),
    Mechanic.RESOURCE_MANAGEMENT: ("Create informed tradeoffs", "Allocate limited resources", "Update budgets and consequences", "Transparent resource displays"),
    Mechanic.PROGRESSION: ("Reward mastery", "Complete challenges", "Unlock meaningful alternatives", "Clear milestones and unlock cues"),
    Mechanic.COOPERATION: ("Encourage coordination", "Coordinate complementary actions", "Synchronize shared objectives", "Shared success indicators"),
    Mechanic.PHYSICS: ("Enable intuitive experimentation", "Apply forces to objects", "Resolve deterministic interactions", "Consistent motion and impact cues"),
    Mechanic.LEVEL_DESIGN: ("Guide pacing and discovery", "Navigate branching challenges", "Balance challenge and recovery", "Readable paths and landmarks"),
    Mechanic.USER_INTERFACE: ("Keep decisions legible", "Inspect and select options", "Respond consistently to input", "Accessible focus and state indicators"),
}


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _constraint(constraints: GameDesignConstraint) -> None:
    if not 2 <= len(constraints.genre.strip()) <= 80:
        raise ValueError("invalid game genre")
    if not 2 <= len(constraints.target_platform.strip()) <= 80:
        raise ValueError("invalid target platform")
    if not 1 <= constraints.max_complexity <= 20:
        raise ValueError("invalid complexity budget")
    for group in (constraints.accessibility, constraints.originality_notes):
        if len(group) > 30 or any(
            not isinstance(x, str) or not 1 <= len(x.strip()) <= 200
            for x in group
        ):
            raise ValueError("invalid design constraints")


class DragonGameForge:
    def __init__(self, policy: ForgePolicy = ForgePolicy()):
        if not 2 <= policy.max_candidates <= 10000:
            raise ValueError("invalid candidate budget")
        if not 1 <= policy.max_iterations <= 100000:
            raise ValueError("invalid iteration budget")
        if not 1 <= policy.max_mechanics <= 16:
            raise ValueError("invalid mechanic budget")
        if not isfinite(policy.minimum_confidence) or not 0 <= policy.minimum_confidence <= 1:
            raise ValueError("invalid confidence threshold")
        self.policy = policy

    def propose(self, taste: GameTasteProfile,
                constraints: GameDesignConstraint, *,
                authorized: bool, seed: int = 0) -> GamePrototypeSpec:
        if not authorized:
            raise PermissionError("game design requires authorization")
        if not isinstance(seed, int) or not 0 <= seed <= 1000000:
            raise ValueError("invalid candidate seed")
        _constraint(constraints)
        selected = [
            insight for insight in taste.insights
            if insight.confidence >= self.policy.minimum_confidence
            and insight.preference_score > 0
            and (insight.user_confirmed or not self.policy.require_confirmed_taste)
        ]
        selected.sort(key=lambda x: (
            -x.preference_score, -x.confidence, x.mechanic.value,
        ))
        if not selected:
            raise ValueError("no positive, sufficiently reliable taste signals")
        offset = seed % len(selected)
        rotated = selected[offset:] + selected[:offset]
        designs = []
        for insight in rotated[:self.policy.max_mechanics]:
            goal, action, response, feedback = _MECHANICS[insight.mechanic]
            designs.append(GameMechanicDesign(
                insight.mechanic, goal, action, response, feedback,
                "Test input response, fairness, accessibility and player feedback",
            ))
        candidate_id = _digest([
            taste.fingerprint, constraints.genre, constraints.target_platform,
            [d.mechanic.value for d in designs], seed,
        ])
        return GamePrototypeSpec(
            candidate_id, f"{constraints.genre.strip().title()} Concept {seed + 1}",
            "Create an original experience aligned with confirmed player preferences",
            tuple(designs), constraints, taste.fingerprint,
        )

    def evaluate(self, spec: GamePrototypeSpec, taste: GameTasteProfile,
                 *, authorized: bool) -> ForgeEvaluation:
        if not authorized:
            raise PermissionError("game evaluation requires authorization")
        if spec.source_taste_fingerprint != taste.fingerprint:
            raise ValueError("stale taste profile; regenerate prototype")
        _constraint(spec.constraints)
        scores = {
            insight.mechanic: insight.preference_score * insight.confidence
            for insight in taste.insights if insight.user_confirmed
        }
        mechanics = [item.mechanic for item in spec.mechanics]
        if len(set(mechanics)) != len(mechanics):
            raise ValueError("duplicate mechanics")
        if not mechanics:
            raise ValueError("empty prototype")
        taste_alignment = sum(scores.get(m, 0) for m in mechanics) / len(mechanics)
        positives = {m for m, score in scores.items() if score > 0}
        coverage = len(positives.intersection(mechanics)) / max(1, len(positives))
        accessibility = min(1.0, 0.5 + 0.1 * len(spec.constraints.accessibility))
        complexity = min(1.0, len(mechanics) / spec.constraints.max_complexity)
        total = round(
            0.5 * taste_alignment + 0.3 * coverage
            + 0.2 * accessibility - 0.1 * max(0, complexity - 1),
            5,
        )
        warnings = []
        if not spec.constraints.originality_notes:
            warnings.append("Originality review and independent asset design required")
        if complexity >= 1:
            warnings.append("Mechanic complexity at or above target budget")
        if not spec.constraints.accessibility:
            warnings.append("Accessibility requirements not specified")
        return ForgeEvaluation(
            spec.candidate_id, round(taste_alignment, 5),
            round(coverage, 5), round(accessibility, 5),
            round(complexity, 5), total, tuple(warnings),
        )

    def compete(self, taste: GameTasteProfile,
                constraints: GameDesignConstraint, *,
                authorized: bool, rounds: int = 100) -> ForgeCompetition:
        if not authorized:
            raise PermissionError("competition requires authorization")
        if not 2 <= rounds <= min(self.policy.max_iterations,
                                 self.policy.max_candidates):
            raise ValueError("competition exceeds evaluation budget")
        proposals = []
        for seed in range(rounds):
            proposal = self.propose(taste, constraints,
                                    authorized=True, seed=seed)
            score = self.evaluate(proposal, taste, authorized=True)
            proposals.append((proposal, score))
        proposals.sort(key=lambda x: (-x[1].total, x[0].candidate_id))
        winner, winner_score = proposals[0]
        runner, runner_score = proposals[1]
        return ForgeCompetition(
            winner, runner, winner_score, runner_score, rounds,
            _digest([taste.fingerprint, rounds, winner.candidate_id,
                     runner.candidate_id, winner_score.total]),
        )
