"""Replay-backed discovery and selection for Dragon's original practice games.

Difficulty is a measured route/property estimate, not an AI-generated player
preference, release certificate or a replacement for playtesting.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .contracts import canonical_digest
from .practice_game_library import load_practice_game, list_practice_games
from .playable_simulation import GameReplay, verify_replay


class PracticeSelectionError(ValueError):
    """Invalid bounded practice-game query or unverifiable candidate."""


@dataclass(frozen=True, slots=True)
class PracticeGameSummary:
    game_id: str
    title: str
    theme: str
    width: int
    height: int
    collectible_count: int
    hazard_count: int
    solution_steps: int
    world_digest: str

    @property
    def route_cost(self) -> int:
        """Fixed reference-route effort plus objective and hazard exposure."""
        return self.solution_steps + 4 * self.collectible_count + 3 * self.hazard_count

    def to_payload(self) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "title": self.title,
            "theme": self.theme,
            "width": self.width,
            "height": self.height,
            "collectible_count": self.collectible_count,
            "hazard_count": self.hazard_count,
            "solution_steps": self.solution_steps,
            "route_cost": self.route_cost,
            "world_digest": self.world_digest,
            "release_authorized": False,
        }


def practice_game_catalog(*, authorized: bool) -> tuple[PracticeGameSummary, ...]:
    if authorized is not True:
        raise PermissionError("practice game catalog requires authorization")
    results = []
    worlds = set()
    for game_id in list_practice_games(authorized=True):
        game = load_practice_game(game_id, authorized=True)
        world = game.world
        if world.digest in worlds or game.proof.final_state.status != "won":
            raise PracticeSelectionError("duplicate or unverified practice game")
        worlds.add(world.digest)
        level = world.levels[0]
        results.append(PracticeGameSummary(
            game_id, world.intent.title, world.intent.theme,
            level.width, level.height, len(level.collectibles),
            len(level.hazards), len(game.proof.action_receipts), world.digest,
        ))
    return tuple(results)


def filter_practice_games(
    *, authorized: bool, theme: str | None = None,
    min_solution_steps: int = 0, max_solution_steps: int = 20000,
    max_hazards: int = 24, limit: int = 100,
) -> tuple[PracticeGameSummary, ...]:
    """Deterministic, bounded selectors for the companion/editor UI."""
    if authorized is not True:
        raise PermissionError("practice game discovery requires authorization")
    if theme is not None and theme not in {
        "forest", "space", "desert", "ocean", "arcade",
    }:
        raise PracticeSelectionError("unknown original game theme")
    if (type(min_solution_steps) is not int or type(max_solution_steps) is not int
            or not 0 <= min_solution_steps <= max_solution_steps <= 20000
            or type(max_hazards) is not int or not 0 <= max_hazards <= 24
            or type(limit) is not int or not 1 <= limit <= 100):
        raise PracticeSelectionError("invalid practice game selection budget")
    candidates = (
        item for item in practice_game_catalog(authorized=True)
        if (theme is None or item.theme == theme)
        and min_solution_steps <= item.solution_steps <= max_solution_steps
        and item.hazard_count <= max_hazards
    )
    return tuple(sorted(
        candidates, key=lambda x: (x.route_cost, x.game_id),
    ))[:limit]


def plan_practice_progression(
    *, authorized: bool, count: int = 8, theme: str | None = None,
) -> tuple[PracticeGameSummary, ...]:
    """Select an increasing verified-route sequence across a difficulty range.

    The order is a transparent heuristic and cannot be used as evidence of
    learned skill, user preference, model training or hardware mastery.
    """
    if authorized is not True:
        raise PermissionError("practice progression planning requires authorization")
    if type(count) is not int or not 1 <= count <= 20:
        raise PracticeSelectionError("practice progression count must be 1..20")
    available = filter_practice_games(
        authorized=True, theme=theme, limit=100,
    )
    if len(available) < count:
        raise PracticeSelectionError("not enough verified games for progression")
    if count == 1:
        return (available[0],)
    indices = [
        i * (len(available) - 1) // (count - 1)
        for i in range(count)
    ]
    if len(set(indices)) != count:
        raise PracticeSelectionError("practice progression repeated a game")
    return tuple(available[index] for index in indices)


def verified_practice_run(
    game_id: str, replay: GameReplay, *, authorized: bool,
) -> dict[str, object]:
    """Re-simulate a player attempt; emit a privacy-light result receipt."""
    if authorized is not True:
        raise PermissionError("practice run verification requires authorization")
    if not isinstance(replay, GameReplay):
        raise PracticeSelectionError("typed practice replay required")
    game = load_practice_game(game_id, authorized=True)
    verify_replay(game.world, replay, authorized=True)
    state = replay.final_state
    return {
        "schema": "skeleton.dragon.practice_game_attempt.v1",
        "game_id": game_id,
        "world_digest": game.world.digest,
        "replay_digest": replay.digest,
        "status": state.status,
        "health_remaining": state.health,
        "score": state.score,
        "steps": state.steps,
        "reference_solution_steps": len(game.proof.action_receipts),
        "completed": state.status == "won",
        "independent_quality_approved": False,
        "training_authorized": False,
        "memory_promotion_authorized": False,
    }
