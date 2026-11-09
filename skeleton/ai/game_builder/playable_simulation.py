"""Executable turn simulation and reproducible replay of game-builder worlds.

This is the Python reference for the browser's step-based keyboard/touch game.
World generation and game simulation do real work without a provider or a
network connection. Causal replay is over typed actions and content hashes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Sequence

from .contracts import canonical_digest, canonical_json
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

    def __post_init__(self) -> None:
        if type(self.index) is not int or not 0 <= self.index < MAX_REPLAY_ACTIONS:
            raise GameplayError("invalid action receipt index")
        if type(self.action) is not str or self.action not in _MOVES:
            raise GameplayError("invalid action receipt control")
        for name in ("before_digest", "after_digest"):
            value = getattr(self, name)
            if type(value) is not str or len(value) != 64 or any(
                ch not in "0123456789abcdef" for ch in value
            ):
                raise GameplayError(f"invalid receipt {name}")
        if self.prev_receipt_digest is not None and (
            type(self.prev_receipt_digest) is not str
            or len(self.prev_receipt_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.prev_receipt_digest)
        ):
            raise GameplayError("invalid previous receipt digest")

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

    def __post_init__(self) -> None:
        if (type(self.world_digest) is not str or len(self.world_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in self.world_digest)):
            raise GameplayError("replay world digest invalid")
        if (type(self.initial_state_digest) is not str
                or len(self.initial_state_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in self.initial_state_digest)):
            raise GameplayError("replay initial state digest invalid")
        if (not isinstance(self.action_receipts, tuple)
                or len(self.action_receipts) > MAX_REPLAY_ACTIONS
                or any(not isinstance(row, ActionReceipt) for row in self.action_receipts)):
            raise GameplayError("replay receipt collection invalid")
        if not isinstance(self.final_state, PlayState):
            raise GameplayError("replay final state invalid")
        if self.world_digest != self.final_state.world_digest:
            raise GameplayError("replay and final state world mismatch")
        if self.action_receipts and (
            self.action_receipts[-1].after_digest != self.final_state.digest
            or self.action_receipts[0].before_digest != self.initial_state_digest
        ):
            raise GameplayError("replay boundary receipts invalid")

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
    if authorized is not True:
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
    if authorized is not True:
        raise PermissionError("game action requires authorization")
    _assert_state(world, state)
    if not isinstance(action, str) or action not in _MOVES:
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
    if authorized is not True:
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
    if authorized is not True:
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



def replay_prefix(
    world: PlayableWorld, replay: GameReplay, count: int, *,
    authorized: bool,
) -> GameReplay:
    """Seek to an independently verified action boundary without trusting the
    stored final state or its untrusted chain of intermediate receipts.
    """
    if authorized is not True:
        raise PermissionError("replay seeking requires authorization")
    if type(count) is not int or not 0 <= count <= MAX_REPLAY_ACTIONS:
        raise GameplayError("replay seek count out of bounds")
    verify_replay(world, replay, authorized=True)
    if count > len(replay.action_receipts):
        raise GameplayError("replay prefix exceeds verified history")
    if count == len(replay.action_receipts):
        return replay
    state = initial_state(world, authorized=True)
    for receipt in replay.action_receipts[:count]:
        state = advance(world, state, receipt.action, authorized=True)
    return GameReplay(
        world.digest, replay.action_receipts[:count], state,
        replay.initial_state_digest,
    )



def resume_replay(
    world: PlayableWorld, replay: GameReplay, actions: Sequence[str], *,
    authorized: bool,
) -> GameReplay:
    """Continue an authenticated, verified replay without recomputing its
    committed receipt hash chain. No continuation may rewrite prior actions.
    """
    if authorized is not True:
        raise PermissionError("replay continuation requires authorization")
    verify_replay(world, replay, authorized=True)
    if (not isinstance(actions, (tuple, list))
            or len(replay.action_receipts) + len(actions) > MAX_REPLAY_ACTIONS):
        raise GameplayError("replay continuation exceeds action budget")
    if replay.final_state.status != "playing" and actions:
        raise GameplayError("terminal gameplay cannot resume")
    receipts = list(replay.action_receipts)
    state = replay.final_state
    for action in actions:
        before_digest = state.digest
        state = advance(world, state, action, authorized=True)
        receipts.append(ActionReceipt(
            len(receipts), action, before_digest, state.digest,
            receipts[-1].digest if receipts else None,
        ))
    output = GameReplay(
        world.digest, tuple(receipts), state, replay.initial_state_digest,
    )
    verify_replay(world, output, authorized=True)
    return output


def fork_replay(
    world: PlayableWorld, replay: GameReplay, at_step: int,
    alternative_actions: Sequence[str], *, authorized: bool,
) -> GameReplay:
    """Create a reversible alternative playthrough from a validated prefix.

    Never mutate the original replay and never import a foreign-world
    checkpoint. The committed prefix receipts remain byte-identical.
    """
    if authorized is not True:
        raise PermissionError("replay branching requires authorization")
    prefix = replay_prefix(world, replay, at_step, authorized=True)
    return resume_replay(world, prefix, alternative_actions, authorized=True)



def replay_divergence(
    world: PlayableWorld, first: GameReplay, second: GameReplay, *,
    authorized: bool,
) -> int | None:
    """Earliest move at which two *verified* replay histories differ.

    A strict prefix is considered divergent at the missing next move.
    This does not infer player preference or grant any quality promotion.
    """
    if authorized is not True:
        raise PermissionError("replay comparison requires authorization")
    verify_replay(world, first, authorized=True)
    verify_replay(world, second, authorized=True)
    shared = min(len(first.action_receipts), len(second.action_receipts))
    for index in range(shared):
        if first.action_receipts[index].digest != second.action_receipts[index].digest:
            return index
    if len(first.action_receipts) != len(second.action_receipts):
        return shared
    return None



MAX_SERIALIZED_REPLAY_BYTES = 12 * 1024 * 1024


def serialize_replay(
    world: PlayableWorld, replay: GameReplay, *, authorized: bool,
) -> bytes:
    """Produce a bounded, canonical offline-save blob with replay custody.

    No user credential, unreviewed assets or executable code is embedded.
    The world remains a separately verified source of gameplay authority.
    """
    if authorized is not True:
        raise PermissionError("replay serialization requires authorization")
    verify_replay(world, replay, authorized=True)
    raw = canonical_json({
        "schema": "skeleton.game_builder.offline-replay-save.v1",
        "world_digest": world.digest,
        "replay": replay.to_payload(),
        "replay_digest": replay.digest,
    }).encode("ascii")
    if not 0 < len(raw) <= MAX_SERIALIZED_REPLAY_BYTES:
        raise GameplayError("offline replay save exceeds byte budget")
    return raw



def deserialize_replay(
    world: PlayableWorld, data: bytes, *, authorized: bool,
) -> GameReplay:
    """Reconstruct an offline-save replay without accepting ambiguous JSON.

    The archived action chain is never trusted: every move is executed again
    against the supplied, digest-matched original game world.
    """
    if authorized is not True:
        raise PermissionError("offline replay restore requires authorization")
    if (type(data) is not bytes or not 0 < len(data) <= MAX_SERIALIZED_REPLAY_BYTES):
        raise GameplayError("offline replay save has invalid byte budget")

    def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for name, item in pairs:
            if name in value:
                raise GameplayError("duplicate offline replay JSON key")
            value[name] = item
        return value

    def _finite(value: str) -> None:
        raise GameplayError("nonfinite offline replay JSON number")

    try:
        payload = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_unique,
            parse_constant=_finite,
        )
        if type(payload) is not dict or canonical_json(payload).encode("ascii") != data:
            raise GameplayError("offline replay JSON not canonical")
    except (UnicodeError, TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise GameplayError("invalid offline replay JSON") from exc

    if (
        set(payload) != {"schema", "world_digest", "replay", "replay_digest"}
        or payload["schema"] != "skeleton.game_builder.offline-replay-save.v1"
        or payload["world_digest"] != world.digest
    ):
        raise GameplayError("offline replay save world or schema mismatch")
    document = payload["replay"]
    if (
        type(document) is not dict
        or set(document) != {
            "schema", "world_digest", "initial_state_digest", "actions", "final_state",
        }
        or document["schema"] != "skeleton.game_builder.game_replay.v1"
        or type(document["actions"]) is not list
        or len(document["actions"]) > MAX_REPLAY_ACTIONS
    ):
        raise GameplayError("offline replay document shape invalid")
    state = document["final_state"]
    if (
        type(state) is not dict
        or set(state) != {
            "world_digest", "level_index", "x", "y", "collected",
            "health", "steps", "score", "status",
        }
        or type(state["collected"]) is not list
        or len(state["collected"]) > MAX_COLLECTIBLES
        or any(type(pair) is not list or len(pair) != 2 for pair in state["collected"])
    ):
        raise GameplayError("offline replay state shape invalid")
    try:
        restored = PlayState(
            state["world_digest"], state["level_index"], state["x"], state["y"],
            tuple(tuple(point) for point in state["collected"]),
            state["health"], state["steps"], state["score"], state["status"],
        )
        receipts: list[ActionReceipt] = []
        for entry in document["actions"]:
            if type(entry) is not dict or set(entry) != {
                "index", "action", "before_digest", "after_digest",
                "prev_receipt_digest", "digest",
            }:
                raise GameplayError("offline replay receipt shape invalid")
            row = ActionReceipt(
                entry["index"], entry["action"], entry["before_digest"],
                entry["after_digest"], entry["prev_receipt_digest"],
            )
            if entry["digest"] != row.digest:
                raise GameplayError("offline replay receipt digest mismatch")
            receipts.append(row)
        replay = GameReplay(
            document["world_digest"], tuple(receipts), restored,
            document["initial_state_digest"],
        )
    except (TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
        raise GameplayError("offline replay fields invalid") from exc
    if replay.digest != payload["replay_digest"]:
        raise GameplayError("offline replay root identity mismatch")
    verify_replay(world, replay, authorized=True)
    return replay


def demonstrate_solvable(world: PlayableWorld, *, authorized: bool) -> GameReplay:
    """Execute each level's hazard-free proof with the real transition engine."""
    if authorized is not True:
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
    "replay_prefix", "resume_replay", "fork_replay", "replay_divergence",
    "serialize_replay", "deserialize_replay", "demonstrate_solvable",
    "MAX_REPLAY_ACTIONS", "MAX_SERIALIZED_REPLAY_BYTES",
]
