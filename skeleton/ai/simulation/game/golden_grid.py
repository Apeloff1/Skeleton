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
