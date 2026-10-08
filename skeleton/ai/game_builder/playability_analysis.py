"""Verified replay metrics for original playable games and reviewed UX iteration.

Heuristics flag practical gameplay problems rather than fabricate an empirical
model of users. Sources are deterministic, typed action histories executed by
the canonical reference simulation; no raw videos or personal IDs are stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import canonical_digest
from .playable_world import PlayableWorld
from .playable_simulation import (
    GameReplay, GameplayError, advance, initial_state, verify_replay,
)


MAX_COHORT = 1000


class PlayabilityAnalysisError(ValueError):
    """A replay or cohort cannot be treated as reliable gameplay evidence."""


@dataclass(frozen=True, slots=True)
class LevelExperience:
    level_index: int
    completed: bool
    moves: int
    shortest_safe_route: int
    wall_contacts: int
    revisit_moves: int
    backtracks: int
    unique_tiles_visited: int
    hazard_hits: int
    collectibles_found: int
    collectibles_total: int
    first_collectible_move: int | None

    @property
    def route_overrun_ppm(self) -> int | None:
        if not self.completed:
            return None
        return self.moves * 1_000_000 // max(1, self.shortest_safe_route)

    @property
    def wall_friction_ppm(self) -> int:
        return self.wall_contacts * 1_000_000 // max(1, self.moves)

    @property
    def revisit_ppm(self) -> int:
        return self.revisit_moves * 1_000_000 // max(1, self.moves)

    def to_payload(self) -> dict[str, object]:
        return {
            "level_index": self.level_index,
            "completed": self.completed, "moves": self.moves,
            "shortest_safe_route": self.shortest_safe_route,
            "wall_contacts": self.wall_contacts, "revisit_moves": self.revisit_moves,
            "backtracks": self.backtracks,
            "unique_tiles_visited": self.unique_tiles_visited,
            "hazard_hits": self.hazard_hits,
            "collectibles_found": self.collectibles_found,
            "collectibles_total": self.collectibles_total,
            "first_collectible_move": self.first_collectible_move,
            "route_overrun_ppm": self.route_overrun_ppm,
            "wall_friction_ppm": self.wall_friction_ppm,
            "revisit_ppm": self.revisit_ppm,
        }


@dataclass(frozen=True, slots=True)
class PlayabilityFinding:
    level_index: int
    signal: str
    severity: str
    evidence_digest: str
    suggestion: str

    def __post_init__(self) -> None:
        if self.signal not in {
            "wall_friction", "navigation_revisits", "route_overrun",
            "hazard_damage", "incomplete_objectives",
        }:
            raise PlayabilityAnalysisError("unsupported friction signal")
        if self.severity not in {"attention", "strong"}:
            raise PlayabilityAnalysisError("unsupported finding severity")
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) != 64:
            raise PlayabilityAnalysisError("finding evidence digest required")

    def to_payload(self) -> dict[str, object]:
        return {
            "level_index": self.level_index,
            "signal": self.signal, "severity": self.severity,
            "evidence_digest": self.evidence_digest,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True, slots=True)
class PlayabilityReport:
    world_digest: str
    replay_digest: str
    completed_game: bool
    levels: tuple[LevelExperience, ...]
    findings: tuple[PlayabilityFinding, ...]
    no_preference_inference: bool = True

    def to_payload(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": "skeleton.game_builder.playability_report.v1",
            "world_digest": self.world_digest,
            "replay_digest": self.replay_digest,
            "completed_game": self.completed_game,
            "levels": [level.to_payload() for level in self.levels],
            "findings": [finding.to_payload() for finding in self.findings],
            "no_preference_inference": self.no_preference_inference,
            "requires_human_evaluation": True,
            "improvement_proposals_are_nonexecuting": True,
        }
        return {**body, "report_digest": canonical_digest(body)}


class _LevelCounters:
    def __init__(self, level_index: int, start: tuple[int, int]) -> None:
        self.level_index = level_index
        self.moves = 0
        self.wall_contacts = 0
        self.revisit_moves = 0
        self.backtracks = 0
        self.hazard_hits = 0
        self.collectibles_found = 0
        self.first_collectible_move = None
        self.visits = {start}
        self.previous_position: tuple[int, int] | None = None
        self.completed = False

    def step(
        self,
        before: tuple[int, int],
        after: tuple[int, int],
        health_lost: int,
        pickups: int,
        completed: bool,
    ) -> None:
        self.moves += 1
        if before == after:
            self.wall_contacts += 1
        else:
            if after in self.visits:
                self.revisit_moves += 1
            if self.previous_position is not None and after == self.previous_position:
                self.backtracks += 1
            self.visits.add(after)
        self.previous_position = before
        self.hazard_hits += health_lost
        self.collectibles_found += pickups
        if pickups and self.first_collectible_move is None:
            self.first_collectible_move = self.moves
        self.completed = completed or self.completed

    def summarize(self, world: PlayableWorld) -> LevelExperience:
        level = world.levels[self.level_index]
        return LevelExperience(
            self.level_index, self.completed, self.moves, len(level.safe_solution),
            self.wall_contacts, self.revisit_moves, self.backtracks,
            len(self.visits), self.hazard_hits, self.collectibles_found,
            len(level.collectibles), self.first_collectible_move,
        )


_SUGGESTIONS = {
    "wall_friction": (
        "Review wall visibility and input-response cues; inspect blocked-move "
        "positions with a player before changing geometry."
    ),
    "navigation_revisits": (
        "Add clearer original landmarks or navigation hints, then compare "
        "independent replays before changing the layout."
    ),
    "route_overrun": (
        "Inspect pacing and optional detours versus the verified safe route; "
        "consider reducing unnecessary traversal cost."
    ),
    "hazard_damage": (
        "Review hazard telegraphing, safe approach space and recovery feedback "
        "with accessibility needs in mind."
    ),
    "incomplete_objectives": (
        "Check crystal visibility and exit feedback; ask for playtest observations "
        "before inferring a design defect."
    ),
}


def _findings(level: LevelExperience) -> tuple[PlayabilityFinding, ...]:
    flags: list[tuple[str, str]] = []
    if level.moves >= 5 and level.wall_friction_ppm >= 200_000:
        flags.append(("wall_friction", "strong" if level.wall_friction_ppm >= 400_000 else "attention"))
    if level.moves >= 10 and level.revisit_ppm >= 300_000:
        flags.append(("navigation_revisits", "strong" if level.revisit_ppm >= 500_000 else "attention"))
    if level.route_overrun_ppm is not None and level.route_overrun_ppm > 1_500_000:
        flags.append(("route_overrun", "strong" if level.route_overrun_ppm > 3_000_000 else "attention"))
    if level.hazard_hits:
        flags.append(("hazard_damage", "strong" if level.hazard_hits > 1 else "attention"))
    if level.moves >= max(12, level.shortest_safe_route) and not level.completed:
        flags.append(("incomplete_objectives", "attention"))
    evidence = canonical_digest(level.to_payload())
    return tuple(
        PlayabilityFinding(level.level_index, signal, severity, evidence, _SUGGESTIONS[signal])
        for signal, severity in flags
    )


def analyze_replay(
    world: PlayableWorld, replay: GameReplay, *,
    authorized: bool,
) -> PlayabilityReport:
    """Replay *every* action, compute movement friction, and keep findings advisory."""
    if not authorized:
        raise PermissionError("gameplay evidence analysis requires authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(replay, GameReplay):
        raise PlayabilityAnalysisError("typed world and verified replay required")
    verify_replay(world, replay, authorized=True)
    state = initial_state(world, authorized=True)
    counters = [
        _LevelCounters(level.index, level.start) for level in world.levels
    ]
    touched: set[int] = {0}
    for receipt in replay.action_receipts:
        before = state
        state = advance(world, state, receipt.action, authorized=True)
        index = before.level_index
        touched.add(index)
        before_position = (before.x, before.y)
        after_position = (
            (state.x, state.y) if state.level_index == index
            else world.levels[index].exit
        )
        before_set = set(before.collected)
        after_set = (
            set(state.collected) if state.level_index == index
            else set(world.levels[index].collectibles)
        )
        counters[index].step(
            before_position, after_position,
            before.health - state.health,
            len(after_set - before_set),
            state.level_index > index or state.status == "won",
        )
        touched.add(state.level_index)
    levels = tuple(counters[index].summarize(world) for index in sorted(touched))
    findings = tuple(
        finding for level in levels for finding in _findings(level)
    )
    return PlayabilityReport(
        world.digest, replay.digest, state.status == "won", levels, findings,
    )


@dataclass(frozen=True, slots=True)
class CohortExperience:
    world_digest: str
    sample_count: int
    completed_count: int
    total_attempted_moves: int
    total_wall_contacts: int
    total_hazard_hits: int
    total_objectives_found: int
    flagged_level_indices: tuple[int, ...]
    report_digests: tuple[str, ...]
    empirical_claims_not_calibrated: bool = True

    def to_payload(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": "skeleton.game_builder.playability_cohort.v1",
            "world_digest": self.world_digest,
            "sample_count": self.sample_count,
            "completed_count": self.completed_count,
            "completion_rate_ppm": self.completed_count * 1_000_000 // self.sample_count,
            "total_attempted_moves": self.total_attempted_moves,
            "total_wall_contacts": self.total_wall_contacts,
            "total_hazard_hits": self.total_hazard_hits,
            "total_objectives_found": self.total_objectives_found,
            "flagged_level_indices": list(self.flagged_level_indices),
            "report_digests": list(self.report_digests),
            "empirical_claims_not_calibrated": self.empirical_claims_not_calibrated,
            "requires_independent_playtest_review": True,
        }
        return {**body, "cohort_digest": canonical_digest(body)}


def aggregate_playability(
    world: PlayableWorld,
    reports: Sequence[PlayabilityReport],
    *,
    authorized: bool,
    consent_to_aggregate: bool,
) -> CohortExperience:
    """Consent-gated aggregate with replay-identity deduplication.

    All of the reports must refer to one exact game world. Duplicate traces
    are rejected rather than being counted as independent playtesters.
    """
    if not authorized:
        raise PermissionError("playtest cohort analysis requires authorization")
    if type(consent_to_aggregate) is not bool or not consent_to_aggregate:
        raise PlayabilityAnalysisError("explicit playtest aggregation consent required")
    if not isinstance(world, PlayableWorld) or not isinstance(reports, (tuple, list)):
        raise PlayabilityAnalysisError("typed world and report collection required")
    if not 3 <= len(reports) <= MAX_COHORT:
        raise PlayabilityAnalysisError("cohort requires 3 to 1000 independent replay records")
    if any(not isinstance(row, PlayabilityReport) or row.world_digest != world.digest
           or not row.no_preference_inference for row in reports):
        raise PlayabilityAnalysisError("untrusted or mismatched cohort report")
    identifiers = [row.replay_digest for row in reports]
    if len(set(identifiers)) != len(identifiers):
        raise PlayabilityAnalysisError("duplicate action trace in playtest cohort")
    levels = [level for report in reports for level in report.levels]
    flags = tuple(sorted({
        finding.level_index for report in reports for finding in report.findings
    }))
    return CohortExperience(
        world.digest, len(reports),
        sum(report.completed_game for report in reports),
        sum(item.moves for item in levels),
        sum(item.wall_contacts for item in levels),
        sum(item.hazard_hits for item in levels),
        sum(item.collectibles_found for item in levels),
        flags,
        tuple(sorted(report.to_payload()["report_digest"] for report in reports)),
    )


__all__ = [
    "PlayabilityAnalysisError", "LevelExperience", "PlayabilityFinding",
    "PlayabilityReport", "CohortExperience", "analyze_replay",
    "aggregate_playability",
]
