"""Executable turn simulation and reproducible replay of game-builder worlds.

This is the Python reference for the browser's step-based keyboard/touch game.
World generation and game simulation do real work without a provider or a
network connection. Causal replay is over typed actions and content hashes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import canonical_digest
from .playable_world import (
    DIRECTIONS, MAX_COLLECTIBLES, GameBuildIntent, PlayableWorld,
    PlayableWorldError,
)


class GameplayError(ValueError):
    """Invalid input, world identity, state transition or replay."""


MAX_REPLAY_ACTIONS = 20000
_MOVES = {name: (dx, dy) for name, dx, dy in DIRECTIONS}


@dataclass(frozen=True, slots=True)
class PlayState:
    world_digest: str
    level_index: int
    x: int
    y: int
    collected: tuple[tuple[int, int], ...]
    health: int
    steps: int
    score: int
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.world_digest, str) or len(self.world_digest) != 64:
            raise GameplayError("invalid state world digest")
        for name in ("level_index", "x", "y", "health", "steps", "score"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise GameplayError(f"invalid state {name}")
        if self.steps > MAX_REPLAY_ACTIONS:
            raise GameplayError("game step budget exceeded")
        if self.status not in {"playing", "won", "lost"}:
            raise GameplayError("invalid game status")
        if not isinstance(self.collected, tuple) or len(self.collected) > MAX_COLLECTIBLES:
            raise GameplayError("invalid collected objectives")
        if tuple(sorted(set(self.collected))) != self.collected:
            raise GameplayError("collected items must be unique and ordered")
        for item in self.collected:
            if (not isinstance(item, tuple) or len(item) != 2
                    or any(type(v) is not int or v < 0 for v in item)):
                raise GameplayError("invalid collected coordinate")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "world_digest": self.world_digest,
            "level_index": self.level_index, "x": self.x, "y": self.y,
            "collected": [list(item) for item in self.collected],
            "health": self.health, "steps": self.steps,
            "score": self.score, "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ActionReceipt:
    index: int
    action: str
    before_digest: str
    after_digest: str
    prev_receipt_digest: str | None

    @property
    def digest(self) -> str:
        return canonical_digest({
            "schema": "skeleton.game_builder.action_receipt.v1",
            "index": self.index, "action": self.action,
            "before_digest": self.before_digest, "after_digest": self.after_digest,
            "prev_receipt_digest": self.prev_receipt_digest,
        })

    def to_payload(self) -> dict[str, object]:
        return {
            "index": self.index, "action": self.action,
            "before_digest": self.before_digest, "after_digest": self.after_digest,
            "prev_receipt_digest": self.prev_receipt_digest,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class GameReplay:
    world_digest: str
    action_receipts: tuple[ActionReceipt, ...]
    final_state: PlayState
    initial_state_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.game_replay.v1",
            "world_digest": self.world_digest,
            "initial_state_digest": self.initial_state_digest,
            "actions": [row.to_payload() for row in self.action_receipts],
            "final_state": self.final_state.to_payload(),
        }


def _assert_state(world: PlayableWorld, state: PlayState) -> None:
    if not isinstance(world, PlayableWorld) or not isinstance(state, PlayState):
        raise GameplayError("typed world and PlayState required")
    if state.world_digest != world.digest:
        raise GameplayError("state does not match this world")
    if not 0 <= state.level_index < len(world.levels):
        raise GameplayError("state level out of range")
    level = world.levels[state.level_index]
    if not 0 <= state.y < level.height or not 0 <= state.x < level.width:
        raise GameplayError("state coordinates outside level")
    if level.rows[state.y][state.x] == "#":
        raise GameplayError("state cannot occupy a wall")
    if state.health > world.intent.starting_health:
        raise GameplayError("state health exceeds world limits")
    if any(item not in level.collectibles for item in state.collected):
        raise GameplayError("state contains foreign collectibles")
    if state.score < 0 or state.score > len(world.levels) * (
        world.intent.collectibles_per_level * 10 + 100
    ):
        raise GameplayError("state score outside possible budget")
    if state.status == "lost" and state.health != 0:
        raise GameplayError("lost state must be out of health")
    if state.status in {"playing", "won"} and state.health == 0:
        raise GameplayError("live state has zero health")
    if state.status == "won" and (
        state.level_index != len(world.levels) - 1
        or (state.x, state.y) != level.exit
        or len(state.collected) != len(level.collectibles)
    ):
        raise GameplayError("winning state must complete the final level")


def initial_state(world: PlayableWorld, *, authorized: bool) -> PlayState:
    if not authorized:
        raise PermissionError("game session creation requires authorization")
    if not isinstance(world, PlayableWorld):
        raise GameplayError("PlayableWorld required")
    x, y = world.levels[0].start
    return PlayState(
        world.digest, 0, x, y, (),
        world.intent.starting_health, 0, 0, "playing",
    )


def advance(
    world: PlayableWorld, state: PlayState, action: str, *,
    authorized: bool,
) -> PlayState:
    if not authorized:
        raise PermissionError("game action requires authorization")
    _assert_state(world, state)
    if action not in _MOVES or not isinstance(action, str):
        raise GameplayError("unsupported player action")
    if state.status != "playing":
        raise GameplayError("terminal session cannot accept more actions")
    if state.steps >= MAX_REPLAY_ACTIONS:
        raise GameplayError("maximum session length exceeded")
    level = world.levels[state.level_index]
    dx, dy = _MOVES[action]
    nx, ny = state.x + dx, state.y + dy
    if (not 0 <= nx < level.width or not 0 <= ny < level.height
            or level.rows[ny][nx] == "#"):
        nx, ny = state.x, state.y
    tile = level.rows[ny][nx]
    entered = (nx, ny) != (state.x, state.y)
    collected = set(state.collected)
    score = state.score
    if tile == "C" and (nx, ny) not in collected:
        collected.add((nx, ny))
        score += 10
    health = state.health
    if tile == "H" and entered:
        health -= 1
    status = "playing"
    index = state.level_index
    if health <= 0:
        health = 0
        status = "lost"
    elif tile == "G" and len(collected) == len(level.collectibles):
        score += 100
        if index == len(world.levels) - 1:
            status = "won"
        else:
            index += 1
            nx, ny = world.levels[index].start
            collected.clear()
    output = PlayState(
        world.digest, index, nx, ny,
        tuple(sorted(collected)), health,
        state.steps + 1, score, status,
    )
    _assert_state(world, output)
    return output


def play_actions(
    world: PlayableWorld, actions: Sequence[str], *,
    authorized: bool,
) -> GameReplay:
    if not authorized:
        raise PermissionError("game replay execution requires authorization")
    if not isinstance(actions, (tuple, list)) or len(actions) > MAX_REPLAY_ACTIONS:
        raise GameplayError("invalid or oversized replay action sequence")
    state = initial_state(world, authorized=True)
    initial_digest = state.digest
    receipts: list[ActionReceipt] = []
    for index, action in enumerate(actions):
        before = state.digest
        state = advance(world, state, action, authorized=True)
        receipts.append(ActionReceipt(
            index, action, before, state.digest,
            receipts[-1].digest if receipts else None,
        ))
    replay = GameReplay(world.digest, tuple(receipts), state, initial_digest)
    verify_replay(world, replay, authorized=True)
    return replay


def verify_replay(
    world: PlayableWorld, replay: GameReplay, *,
    authorized: bool,
) -> None:
    if not authorized:
        raise PermissionError("gameplay replay validation requires authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(replay, GameReplay):
        raise GameplayError("typed world and replay required")
    if replay.world_digest != world.digest:
        raise GameplayError("replay uses a different world")
    if len(replay.action_receipts) > MAX_REPLAY_ACTIONS:
        raise GameplayError("replay action budget exceeded")
    state = initial_state(world, authorized=True)
    if state.digest != replay.initial_state_digest:
        raise GameplayError("initial state receipt mismatch")
    previous = None
    for index, row in enumerate(replay.action_receipts):
        if not isinstance(row, ActionReceipt) or row.index != index:
            raise GameplayError("invalid replay receipt ordering")
        if row.prev_receipt_digest != previous or row.before_digest != state.digest:
            raise GameplayError("replay hash-chain mismatch")
        state = advance(world, state, row.action, authorized=True)
        if row.after_digest != state.digest:
            raise GameplayError("replay action state mismatch")
        previous = row.digest
    if replay.final_state != state:
        raise GameplayError("replay final state mismatch")


def demonstrate_solvable(world: PlayableWorld, *, authorized: bool) -> GameReplay:
    """Execute each level's hazard-free proof with the real transition engine."""
    if not authorized:
        raise PermissionError("game solvability execution requires authorization")
    if not isinstance(world, PlayableWorld):
        raise GameplayError("PlayableWorld required")
    actions: list[str] = []
    for level in world.levels:
        actions.extend(level.safe_solution)
    replay = play_actions(world, tuple(actions), authorized=True)
    if replay.final_state.status != "won":
        raise GameplayError("generated world proof failed to complete the game")
    if replay.final_state.health != world.intent.starting_health:
        raise GameplayError("solvability witness unexpectedly entered a hazard")
    return replay


__all__ = [
    "GameplayError", "PlayState", "ActionReceipt", "GameReplay",
    "initial_state", "advance", "play_actions", "verify_replay",
    "demonstrate_solvable", "MAX_REPLAY_ACTIONS",
]
