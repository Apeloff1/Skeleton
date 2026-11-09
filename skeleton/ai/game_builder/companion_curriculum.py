"""Original companion curriculum: diverse runnable practice worlds with evidence.

Produces a bounded, reproducible range of *new* games from a base intent.
It does not import expressions from other games, train a model, or pretend
that a replay-proven puzzle is evidence of player enjoyment. Machine almanac
observations are exact measurements, not hallucinated historical facts.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .contracts import canonical_digest
from .playable_world import (
    GameBuildIntent, MAX_DIMENSION, MAX_LEVELS, PlayableWorld,
)
from .playable_simulation import GameReplay, verify_replay


class CompanionCurriculumError(ValueError):
    """Practice workload is invalid, unverified or misleadingly graded."""


_THEMES = ("arcade", "desert", "forest", "ocean", "space")
_MAX_GAMES = 8


@dataclass(frozen=True, slots=True)
class PracticeInsight:
    world_digest: str
    proof_digest: str
    intent_digest: str
    level_count: int
    objective_count: int
    hazard_count: int
    safe_solution_turns: int
    accessible_floor_tiles: int
    unique_themes_in_cohort: int
    challenge_score: int
    verified_experience: int
    observation: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.companion_insight.v1",
            "world_digest": self.world_digest,
            "proof_digest": self.proof_digest,
            "intent_digest": self.intent_digest,
            "level_count": self.level_count,
            "objective_count": self.objective_count,
            "hazard_count": self.hazard_count,
            "safe_solution_turns": self.safe_solution_turns,
            "accessible_floor_tiles": self.accessible_floor_tiles,
            "unique_themes_in_cohort": self.unique_themes_in_cohort,
            "challenge_score": self.challenge_score,
            "verified_experience": self.verified_experience,
            "observation": self.observation,
            "independent_playtest_evidence": False,
            "learned_model_weights": False,
            "original_content": True,
            "evidence_kind": "executed_python_winning_replay",
        }


def _grow_dimension(n: int, offset: int) -> int:
    return min(MAX_DIMENSION, n + 2 * offset)


def plan_original_companion_intents(
    base: GameBuildIntent, count: int,
) -> tuple[GameBuildIntent, ...]:
    """Deterministically spread a real cohort over distinct design dimensions.

    Variation affects world shape, collectible economy, optional hazards,
    chapter count and theme, not merely RNG seeds. All constrained through
    the original typed GameBuildIntent and canonical generator limits.
    """
    if not isinstance(base, GameBuildIntent):
        raise CompanionCurriculumError("typed original-game intent required")
    if type(count) is not int or not 0 <= count <= _MAX_GAMES:
        raise CompanionCurriculumError("companion curriculum supports 0 to 8 games")
    variants = []
    digest = canonical_digest(base.to_payload())
    offset = int(digest[:2], 16) % len(_THEMES)
    for idx in range(count):
        seed = int(canonical_digest({
            "schema": "skeleton.original_companion_curriculum.v1",
            "parent": digest, "slot": idx,
        })[:15], 16)
        # Preserve globally unique stable IDs at their maximum length.
        prefix = base.project_id[:97].rstrip("._:-")
        identifier = f"{prefix}.c-{digest[:12]}-{idx + 1}"
        theme = _THEMES[(offset + idx) % len(_THEMES)]
        width = _grow_dimension(base.width, idx % 3)
        height = _grow_dimension(base.height, (idx // 2) % 3)
        collectible_count = min(6, max(1, base.collectibles_per_level + (idx % 3) - 1))
        chapter_count = min(MAX_LEVELS, base.levels + (1 if idx % 4 == 3 else 0))
        hazards = min(24, max(0, base.hazards_per_level + (idx % 4) - 1))
        variants.append(replace(
            base,
            project_id=identifier, title=f"Practice {idx + 1}: {base.title}"[:120],
            seed=seed, theme=theme, width=width, height=height,
            collectibles_per_level=collectible_count,
            hazards_per_level=hazards, levels=chapter_count,
        ))
    return tuple(variants)


def measure_original_practice(
    world: PlayableWorld,
    replay: GameReplay,
    *,
    authorized: bool,
    distinct_themes: int = 1,
) -> PracticeInsight:
    """Prove an original game, compute bounded objective playability metrics.

    XP is earned only for actual simulator-completed worlds. This is not a
    quality/fun grade; the assistant must never call these human playtests.
    """
    if not authorized:
        raise PermissionError("companion insight requires authorized proof inspection")
    if not isinstance(world, PlayableWorld) or not isinstance(replay, GameReplay):
        raise CompanionCurriculumError("typed world and executed replay required")
    if type(distinct_themes) is not int or not 1 <= distinct_themes <= len(_THEMES):
        raise CompanionCurriculumError("invalid measured cohort diversity")
    verify_replay(world, replay, authorized=True)
    if replay.final_state.status != "won":
        raise CompanionCurriculumError("practice XP requires a completed winning game")
    if replay.final_state.health != world.intent.starting_health:
        raise CompanionCurriculumError("practice proof must preserve health on safe route")
    width = world.intent.width
    height = world.intent.height
    traversable = sum(
        ch != "#" for level in world.levels for row in level.rows for ch in row
    )
    objectives = sum(len(level.collectibles) for level in world.levels)
    hazards = sum(len(level.hazards) for level in world.levels)
    actions = len(replay.action_receipts)
    if actions == 0 or actions != replay.final_state.steps:
        raise CompanionCurriculumError("winning replay action count mismatch")
    # Heuristic complexity from *observed* generated puzzle dimensions.
    # Not a subjective quality claim, not a measure of human skill.
    complexity = min(
        1000,
        actions // 4 + objectives * 8 + hazards * 2
        + min(100, traversable // 10) + distinct_themes * 3
        + 8 * (len(world.levels) - 1),
    )
    earned = max(1, min(500, 15 + complexity // 3))
    observation = (
        f"Replay solved {len(world.levels)} original level(s) in {actions} turns, "
        f"collecting {objectives} objective(s), with {hazards} hazard tile(s) "
        f"and {traversable} traversable tiles. No human player was tested."
    )
    return PracticeInsight(
        world_digest=world.digest,
        proof_digest=replay.digest,
        intent_digest=canonical_digest(world.intent.to_payload()),
        level_count=len(world.levels),
        objective_count=objectives,
        hazard_count=hazards,
        safe_solution_turns=actions,
        accessible_floor_tiles=traversable,
        unique_themes_in_cohort=distinct_themes,
        challenge_score=complexity,
        verified_experience=earned,
        observation=observation,
    )


def validate_practice_cohort(
    intents: Sequence[GameBuildIntent],
    *,
    parent: GameBuildIntent,
) -> int:
    """Reject repeated/non-original identities and quantify actual diversity."""
    if not isinstance(intents, (tuple, list)) or len(intents) > _MAX_GAMES:
        raise CompanionCurriculumError("bounded practice cohort required")
    if any(not isinstance(item, GameBuildIntent) for item in intents):
        raise CompanionCurriculumError("invalid cohort game intent")
    ids = [item.project_id for item in intents]
    seeds = [item.seed for item in intents]
    if len(ids) != len(set(ids)) or len(seeds) != len(set(seeds)):
        raise CompanionCurriculumError("cohort has repeated identity or generator seed")
    if parent.project_id in ids:
        raise CompanionCurriculumError("training cannot overwrite the parent product")
    if len(intents) > 1 and len({(i.theme, i.width, i.height, i.levels,
                                  i.collectibles_per_level, i.hazards_per_level)
                                 for i in intents}) != len(intents):
        raise CompanionCurriculumError("cohort lacks mechanical diversity")
    return len({item.theme for item in intents})


__all__ = [
    "CompanionCurriculumError", "PracticeInsight",
    "plan_original_companion_intents", "measure_original_practice",
    "validate_practice_cohort",
]
