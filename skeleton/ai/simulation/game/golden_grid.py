"""Bounded deterministic grid gameplay kernel for an original first-playable scene.

This is a simulation contract, not evidence of a native Godot playtest.
The caller owns the renderer, input adapter and durable save publication.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Final

SCHEMA: Final = "skeleton.game.golden_grid.v1"
MAX_TICKS: Final = 1_000_000
MAX_ACTIONS: Final = 4096
ACTIONS: Final = frozenset({"up", "down", "left", "right", "interact", "wait"})
WALLS: Final = frozenset({(2, 1), (2, 2), (2, 3)})
WIDTH: Final = 6
HEIGHT: Final = 5
KEY: Final = (1, 3)
NPC: Final = (4, 1)
EXIT: Final = (5, 4)


class GameplayError(ValueError):
    """Invalid gameplay input, state or replay custody."""


def _integer(value: object, name: str, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise GameplayError(f"invalid {name}")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True, slots=True)
class GridState:
    tick: int = 0
    x: int = 0
    y: int = 0
    has_key: bool = False
    quest_started: bool = False
    quest_completed: bool = False
    ending: bool = False

    def __post_init__(self) -> None:
        _integer(self.tick, "tick", MAX_TICKS)
        _integer(self.x, "x", WIDTH - 1)
        _integer(self.y, "y", HEIGHT - 1)
        if (self.x, self.y) in WALLS:
            raise GameplayError("player inside wall")
        for name in ("has_key", "quest_started", "quest_completed", "ending"):
            if type(getattr(self, name)) is not bool:
                raise GameplayError(f"invalid {name}")
        if self.quest_completed and not (self.has_key and self.quest_started):
            raise GameplayError("impossible completed quest")
        if self.ending and not self.quest_completed:
            raise GameplayError("impossible ending")


def step(state: GridState, action: str) -> GridState:
    """Advance one fixed tick, with collision and reachable quest/ending."""
    if type(state) is not GridState or type(action) is not str or action not in ACTIONS:
        raise GameplayError("invalid action or state")
    if state.tick == MAX_TICKS:
        raise GameplayError("tick budget exhausted")
    if state.ending:
        if action != "wait":
            raise GameplayError("ending is terminal")
        return state
    dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0),
              "right": (1, 0)}.get(action, (0, 0))
    nx, ny = state.x + dx, state.y + dy
    if not (0 <= nx < WIDTH and 0 <= ny < HEIGHT) or (nx, ny) in WALLS:
        nx, ny = state.x, state.y
    has_key = state.has_key or (nx, ny) == KEY
    started = state.quest_started or (action == "interact" and (nx, ny) == NPC)
    completed = state.quest_completed or (started and has_key and action == "interact" and (nx, ny) == NPC)
    ending = completed and action == "interact" and (nx, ny) == EXIT
    return GridState(state.tick + 1, nx, ny, has_key, started, completed, ending)


def play(actions: list[str], initial: GridState | None = None) -> GridState:
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise GameplayError("invalid action trace")
    state = initial if initial is not None else GridState()
    for action in actions:
        state = step(state, action)
    return state


def checkpoint(state: GridState, *, project_sha256: str) -> str:
    """Canonical tamper-evident checkpoint; caller must publish atomically."""
    if type(state) is not GridState or type(project_sha256) is not str or len(project_sha256) != 64 or any(c not in "0123456789abcdef" for c in project_sha256):
        raise GameplayError("invalid checkpoint identity")
    payload = {"schema": SCHEMA, "project_sha256": project_sha256,
               "state": {name: getattr(state, name) for name in GridState.__dataclass_fields__}}
    payload["digest"] = sha256(_canonical(payload)).hexdigest()
    return _canonical(payload).decode()


def restore(raw: str, *, project_sha256: str) -> GridState:
    if type(raw) is not str or len(raw.encode("utf-8")) > 4096:
        raise GameplayError("invalid checkpoint size")
    try:
        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            out: dict[str, object] = {}
            for key, value in pairs:
                if key in out:
                    raise GameplayError("duplicate checkpoint key")
                out[key] = value
            return out
        data = json.loads(raw, object_pairs_hook=unique)
        if type(data) is not dict or set(data) != {"schema", "project_sha256", "state", "digest"}:
            raise GameplayError("invalid checkpoint fields")
        digest = data.pop("digest")
        if type(digest) is not str or sha256(_canonical(data)).hexdigest() != digest:
            raise GameplayError("checkpoint corrupted")
        if data["schema"] != SCHEMA or data["project_sha256"] != project_sha256:
            raise GameplayError("foreign checkpoint")
        state = data["state"]
        if type(state) is not dict or set(state) != set(GridState.__dataclass_fields__):
            raise GameplayError("invalid state fields")
        return GridState(**state)
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise GameplayError("invalid checkpoint") from exc


class ReplayDivergence(GameplayError):
    """A recorded action list did not reproduce the recorded state hash."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__("replay state hash diverged")
        self.expected = expected
        self.actual = actual


class HoldoutRejected(GameplayError):
    """A holdout partition was supplied where only the training partition is admitted."""


def state_hash(state: GridState) -> str:
    """Canonical hash of one grid state. The hash is not a checkpoint blob."""

    if type(state) is not GridState:
        raise GameplayError("invalid state")
    payload = {
        "schema": SCHEMA,
        "state": {name: getattr(state, name) for name in GridState.__dataclass_fields__},
    }
    return sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class RecordedTrace:
    actions: tuple[str, ...]
    state_hash: str

    def __post_init__(self) -> None:
        if (
            type(self.actions) is not tuple
            or len(self.actions) > MAX_ACTIONS
            or any(type(action) is not str or action not in ACTIONS for action in self.actions)
        ):
            raise GameplayError("invalid recorded actions")
        if type(self.state_hash) is not str or len(self.state_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.state_hash
        ):
            raise GameplayError("invalid recorded state hash")


class GridEnvironmentAdapter:
    """Steps the authored golden grid from a fixed initial state."""

    def __init__(self, initial: GridState | None = None) -> None:
        if initial is not None and type(initial) is not GridState:
            raise GameplayError("invalid state")
        self._state = GridState() if initial is None else initial
        self._actions: list[str] = []

    @property
    def state(self) -> GridState:
        return self._state

    def state_hash(self) -> str:
        return state_hash(self._state)

    def step(self, action: str) -> GridState:
        self._state = step(self._state, action)
        self._actions.append(action)
        return self._state

    def run(self, actions: list[str] | tuple[str, ...]) -> str:
        if not isinstance(actions, (list, tuple)) or len(actions) > MAX_ACTIONS:
            raise GameplayError("invalid action trace")
        self._state = GridState()
        self._actions = []
        for action in actions:
            self.step(action)
        return self.state_hash()

    def record(self) -> RecordedTrace:
        return RecordedTrace(tuple(self._actions), self.state_hash())


def record_actions(actions: list[str]) -> RecordedTrace:
    adapter = GridEnvironmentAdapter()
    digest = adapter.run(actions)
    return RecordedTrace(tuple(actions), digest)


def replay_recorded(trace: RecordedTrace) -> str:
    """Replay the recorded actions and refuse a divergent state hash."""

    if type(trace) is not RecordedTrace:
        raise GameplayError("invalid trace")
    actual = GridEnvironmentAdapter().run(trace.actions)
    if actual != trace.state_hash:
        raise ReplayDivergence(trace.state_hash, actual)
    return actual


class TrainPartition:
    """Training rows. A holdout partition is a different type and cannot be admitted here."""

    def __init__(self, rows: tuple[RecordedTrace, ...]) -> None:
        if type(rows) is not tuple or any(type(row) is not RecordedTrace for row in rows):
            raise GameplayError("training partition requires recorded traces")
        self._rows = rows

    def read(self) -> tuple[RecordedTrace, ...]:
        return self._rows


class HoldoutPartition:
    """Evaluation rows. This type is rejected by training admission."""

    def __init__(self, rows: tuple[RecordedTrace, ...]) -> None:
        if type(rows) is not tuple or not rows or any(type(row) is not RecordedTrace for row in rows):
            raise GameplayError("holdout partition requires recorded traces")
        self._rows = rows

    def read(self) -> tuple[RecordedTrace, ...]:
        return self._rows


class GameDataset:
    """Splits recorded traces into distinct partition objects at construction."""

    def __init__(self, traces: list[RecordedTrace] | tuple[RecordedTrace, ...], *, holdout_indexes: set[int]) -> None:
        if not isinstance(traces, (list, tuple)) or not traces or len(traces) > MAX_ACTIONS:
            raise GameplayError("dataset requires a bounded trace list")
        if type(holdout_indexes) is not set or not holdout_indexes:
            raise GameplayError("holdout indexes are required")
        train: list[RecordedTrace] = []
        holdout: list[RecordedTrace] = []
        for index, trace in enumerate(traces):
            if type(trace) is not RecordedTrace:
                raise GameplayError("dataset traces must be recorded")
            if index in holdout_indexes:
                holdout.append(trace)
            else:
                train.append(trace)
        if not holdout or len(holdout_indexes) != len(holdout):
            raise GameplayError("holdout indexes must name existing traces")
        self.train = TrainPartition(tuple(train))
        self.holdout = HoldoutPartition(tuple(holdout))


def evaluation_rows(partition: HoldoutPartition) -> tuple[RecordedTrace, ...]:
    """Read the holdout partition for evaluation."""

    if type(partition) is not HoldoutPartition:
        raise GameplayError("evaluation requires the holdout partition")
    return partition.read()


def training_rows(partition: TrainPartition) -> tuple[RecordedTrace, ...]:
    """Admit only the training partition. A holdout object is rejected."""

    if type(partition) is not TrainPartition:
        raise HoldoutRejected("holdout split rejected as training input")
    return partition.read()
