"""Authoritative, deterministic, source-bound walkable game state engine.

Movement is physical grid collision, and decisions require arrival at an
authored scene marker. All receipts are replayable locally; movement does
not represent real-world observation or proof of completed genre mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .studio_ecosystem_walkable import playable_world_source
from .studio_ecosystem_quest import StudioQuestError

DIRECTIONS = {"up": (0, -1), "down": (0, 1),
              "left": (-1, 0), "right": (1, 0)}


def _sha(payload: object) -> str:
    try:
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                         allow_nan=False, separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StudioQuestError("noncanonical walk replay") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class WalkSession:
    project_id: str
    source_digest: str
    events: tuple[tuple[str, str], ...]
    scene_index: int
    position: tuple[int, int]
    chosen: tuple[tuple[str, str], ...]
    accepted_moves: int
    digest: str

    def receipt(self) -> dict[str, object]:
        return {"schema": "skeleton.game_builder.studio_walk_replay.v1",
                "project_id": self.project_id, "source_digest": self.source_digest,
                "events": [list(e) for e in self.events],
                "scene_index": self.scene_index, "position": list(self.position),
                "choices": [list(e) for e in self.chosen],
                "accepted_moves": self.accepted_moves,
                "session_digest": self.digest,
                "external_evidence_verified": False,
                "native_genre_runtime_verified": False,
                "release_certified": False}


def _compute(documents: Mapping[str, Any],
             events: Sequence[tuple[str, str]]) -> WalkSession:
    world = playable_world_source(documents)
    stages = world["stages"]
    maps = world["maps"]
    x, y = world["spawn"]
    target_x, target_y = world["target"]
    scene = 0
    moved = 0
    history: list[tuple[str, str]] = []
    choices: list[tuple[str, str]] = []
    for event in events:
        if (not isinstance(event, (tuple, list)) or len(event) != 2
                or any(not isinstance(v, str) for v in event)):
            raise StudioQuestError("invalid walk event")
        kind, value = event
        if scene >= len(stages):
            raise StudioQuestError("walk event after authored game completion")
        stage = stages[scene]
        if kind == "move":
            delta = DIRECTIONS.get(value)
            if delta is None:
                raise StudioQuestError("unknown walk direction")
            nx, ny = x + delta[0], y + delta[1]
            if (not 0 <= nx < world["width"] or not 0 <= ny < world["height"]
                    or maps[scene][ny][nx] == "#"):
                raise StudioQuestError("blocked or off-grid movement")
            x, y = nx, ny
            moved += 1
        elif kind == "choose":
            if (value not in stage["alternatives"]
                    or abs(x - target_x) + abs(y - target_y) > 1
                    or not set(stage["prerequisites"]).issubset(
                        {key for key, _ in choices}
                    )):
                raise StudioQuestError("unauthorized or distant scene interaction")
            choices.append((stage["id"], value))
            scene += 1
            x, y = world["spawn"]
        else:
            raise StudioQuestError("unregistered walk action")
        history.append((kind, value))
    state = {"project_id": world["project_id"],
             "source_digest": world["source_digest"],
             "events": history, "scene_index": scene,
             "position": [x, y], "choices": choices,
             "accepted_moves": moved}
    return WalkSession(world["project_id"], world["source_digest"],
                       tuple(history), scene, (x, y), tuple(choices),
                       moved, _sha(state))


def replay_walk(documents: Mapping[str, Any],
                events: Sequence[tuple[str, str]], *, authorized: bool) -> WalkSession:
    if not authorized:
        raise PermissionError("walk game replay requires operator authorization")
    if not isinstance(events, (list, tuple)):
        raise StudioQuestError("walk events must be an ordered sequence")
    return _compute(documents, events)


def start_walk(documents: Mapping[str, Any], *, authorized: bool) -> WalkSession:
    return replay_walk(documents, (), authorized=authorized)


def verify_walk(session: WalkSession, documents: Mapping[str, Any]) -> None:
    if not isinstance(session, WalkSession):
        raise StudioQuestError("invalid walk session")
    if session != _compute(documents, session.events):
        raise StudioQuestError("walk state does not match authoritative replay")


def walk_action(session: WalkSession, documents: Mapping[str, Any], *,
                action: str, value: str, authorized: bool) -> WalkSession:
    if not authorized:
        raise PermissionError("walk movement requires operator authorization")
    verify_walk(session, documents)
    return _compute(documents, session.events + ((action, value),))
