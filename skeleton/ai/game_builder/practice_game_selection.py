"""Replay-backed discovery and selection for Dragon's original practice games.

Difficulty is a measured route/property estimate, not an AI-generated player
preference, release certificate or a replacement for playtesting.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .contracts import canonical_digest
from .practice_game_library import load_practice_game, list_practice_games


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
