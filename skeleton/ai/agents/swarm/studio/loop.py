"""Headless core-loop interpreter.

Role agents assemble a small JSON game. The playtester runs that document
in-process: no model code is executed. A build wins when the scripted policy
can reach the declared win condition inside a tick budget.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping


SCHEMA = "skeleton.studio.loop.v1"


def template_for(genre: str, constraints: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    base = copy.deepcopy(_TEMPLATES.get(genre) or _TEMPLATES["adventure"])
    rooms: dict[str, dict[str, Any]] = base["rooms"]
    win = dict(base["win"])
    if "omit-win-item" in constraints:
        for room in rooms.values():
            room["items"] = []
    if "no-combat" in constraints:
        for room in rooms.values():
            room["enemies"] = []
        win.pop("enemies_cleared", None)
    base["rooms"] = rooms
    base["win"] = win
    base["genre"] = genre if genre in _TEMPLATES else "adventure"
    return base


def assemble_playable(
    brief: Mapping[str, Any],
    *,
    design: Mapping[str, Any],
    level: Mapping[str, Any],
    narrative: Mapping[str, Any],
    art: Mapping[str, Any],
    audio: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "title": brief.get("title") or design.get("fantasy") or "Untitled Game",
        "genre": brief.get("genre") or "adventure",
        "core_loop": list(design.get("core_loop") or []),
        "verbs": list(design.get("verbs") or []),
        "must_include": list(brief.get("must_include") or []),
        "rooms": copy.deepcopy(level.get("rooms") or {}),
        "start_room": level.get("start_room") or "",
        "win": copy.deepcopy(design.get("win") or {}),
        "narrative": {
            "speaker": narrative.get("speaker") or "",
            "beats": list(narrative.get("beats") or []),
        },
        "assets": list(art.get("assets") or []),
        "audio": list(audio.get("cues") or []),
    }


def simulate(playable: Mapping[str, Any], *, max_ticks: int = 32) -> dict[str, Any]:
    """Run the playable headless. Returns boot, tick, verb, and win signals."""
    if not isinstance(max_ticks, int) or isinstance(max_ticks, bool) or not 1 <= max_ticks <= 64:
        raise ValueError("max_ticks must be an integer from 1 to 64")
    if not isinstance(playable, Mapping) or playable.get("schema") != SCHEMA:
        return _boot_failure("schema")
    rooms = playable.get("rooms")
    start = playable.get("start_room")
    if not isinstance(rooms, Mapping) or not isinstance(start, str) or start not in rooms:
        return _boot_failure("start")
    state: dict[str, Any] = {
        "room": start,
        "inventory": [],
        "talked": [],
        "used": [],
        "visited": [start],
        "rooms": copy.deepcopy(rooms),
    }
    verbs: list[str] = []
    phases: list[str] = []
    ticks = 0
    won = False
    try:
        for _ in range(max_ticks):
            action = _choose(playable, state)
            if action is None:
                break
            _apply(action, state)
            verbs.append(action)
            phase = _PHASES.get(action)
            if phase and phase not in phases:
                phases.append(phase)
            ticks += 1
            if _won(playable, state):
                won = True
                break
    except Exception:  # noqa: BLE001 — a crashed loop is a QA signal, not a studio crash
        return {
            "booted": True,
            "ticks": ticks,
            "verbs": verbs,
            "phases": phases,
            "won": False,
            "crashed": True,
            "loop_works": False,
        }
    loop_works = ticks >= 1 and (won or (len(phases) >= 2 and ticks >= 3))
    return {
        "booted": True,
        "ticks": ticks,
        "verbs": verbs,
        "phases": phases,
        "won": won,
        "crashed": False,
        "loop_works": loop_works,
    }


def coverage(playable: Mapping[str, Any], brief: Mapping[str, Any]) -> float:
    expected: list[str] = []
    for key in ("must_include",):
        for item in brief.get(key) or ():
            if isinstance(item, str) and item.strip():
                expected.append(item.strip().lower())
    for item in list(playable.get("core_loop") or []) + list(playable.get("verbs") or []):
        if isinstance(item, str) and item.strip():
            expected.append(item.strip().lower())
    genre = playable.get("genre")
    if isinstance(genre, str) and genre.strip():
        expected.append(genre.strip().lower())
    unique = list(dict.fromkeys(expected))
    if not unique:
        return 0.0
    blob = _blob(playable)
    hits = sum(1 for item in unique if item in blob)
    return hits / len(unique)


def _blob(value: object) -> str:
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, Mapping):
        return " ".join(_blob(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_blob(item) for item in value)
    return ""


def _boot_failure(reason: str) -> dict[str, Any]:
    return {
        "booted": False,
        "ticks": 0,
        "verbs": [],
        "phases": [],
        "won": False,
        "crashed": False,
        "loop_works": False,
        "reason": reason,
    }


def _room(state: dict[str, Any]) -> dict[str, Any]:
    room = state["rooms"].get(state["room"])
    return room if isinstance(room, dict) else {}


def _choose(playable: Mapping[str, Any], state: dict[str, Any]) -> str | None:
    room = _room(state)
    if room.get("enemies"):
        return "attack"
    if room.get("items"):
        return "pickup"
    if room.get("npcs"):
        return "talk"
    interactables = room.get("interactables") or []
    if interactables:
        requires = interactables[0].get("requires")
        if not requires or requires in state["inventory"]:
            return "use"
    exits = room.get("exits") or {}
    for destination in exits.values():
        if destination not in state["visited"]:
            return "move"
    return None


def _apply(action: str, state: dict[str, Any]) -> None:
    room = _room(state)
    if action == "attack":
        enemies = list(room.get("enemies") or [])
        if not enemies:
            raise RuntimeError("nothing to attack")
        enemies.pop(0)
        room["enemies"] = enemies
        return
    if action == "pickup":
        items = list(room.get("items") or [])
        if not items:
            raise RuntimeError("nothing to pick up")
        state["inventory"].append(items.pop(0))
        room["items"] = items
        return
    if action == "talk":
        npcs = list(room.get("npcs") or [])
        if not npcs:
            raise RuntimeError("nobody to talk to")
        state["talked"].append(npcs.pop(0))
        room["npcs"] = npcs
        return
    if action == "use":
        interactables = list(room.get("interactables") or [])
        if not interactables:
            raise RuntimeError("nothing to use")
        state["used"].append(interactables.pop(0).get("id"))
        room["interactables"] = interactables
        return
    if action == "move":
        exits = dict(room.get("exits") or {})
        destination = next(dest for dest in exits.values() if dest not in state["visited"])
        state["room"] = destination
        state["visited"].append(destination)
        return
    raise RuntimeError("unknown action")


def _won(playable: Mapping[str, Any], state: dict[str, Any]) -> bool:
    win = playable.get("win")
    if not isinstance(win, Mapping):
        return False
    if "room" in win and state["room"] != win["room"]:
        return False
    if "has_item" in win and win["has_item"] not in state["inventory"]:
        return False
    if "talked" in win and win["talked"] not in state["talked"]:
        return False
    if "used" in win and win["used"] not in state["used"]:
        return False
    if win.get("enemies_cleared"):
        for room in state["rooms"].values():
            if isinstance(room, dict) and room.get("enemies"):
                return False
    return True


_PHASES = {
    "move": "explore",
    "attack": "fight",
    "pickup": "reward",
    "talk": "act",
    "use": "manipulate",
}


def _room_map(spec: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rooms = {}
    for name, raw in spec.items():
        rooms[name] = {
            "exits": dict(raw.get("exits") or {}),
            "items": list(raw.get("items") or []),
            "enemies": list(raw.get("enemies") or []),
            "npcs": list(raw.get("npcs") or []),
            "interactables": [dict(item) for item in raw.get("interactables") or []],
        }
    return rooms


_TEMPLATES: dict[str, dict[str, Any]] = {
    "rpg": {
        "core_loop": ["explore", "fight", "reward"],
        "verbs": ["move", "attack", "pickup"],
        "start_room": "gate",
        "win": {"room": "yard", "has_item": "key", "enemies_cleared": True},
        "rooms": _room_map(
            {
                "gate": {"exits": {"east": "yard"}, "items": ["key"]},
                "yard": {"exits": {"west": "gate"}, "enemies": ["slime"]},
            }
        ),
    },
    "arcade": {
        "core_loop": ["dodge", "score", "survive"],
        "verbs": ["move", "dodge", "pickup"],
        "start_room": "lane",
        "win": {"room": "finish", "has_item": "coin", "enemies_cleared": True},
        "rooms": _room_map(
            {
                "lane": {"exits": {"east": "finish"}, "enemies": ["barrier"]},
                "finish": {"exits": {"west": "lane"}, "items": ["coin"]},
            }
        ),
    },
    "puzzle": {
        "core_loop": ["observe", "manipulate", "solve"],
        "verbs": ["move", "pickup", "use"],
        "start_room": "bench",
        "win": {"room": "altar", "used": "lever"},
        "rooms": _room_map(
            {
                "bench": {"exits": {"east": "altar"}, "items": ["lens"]},
                "altar": {"interactables": [{"id": "lever", "requires": "lens"}]},
            }
        ),
    },
    "narrative": {
        "core_loop": ["talk", "explore", "choose"],
        "verbs": ["move", "talk"],
        "start_room": "camp",
        "win": {"room": "ending", "talked": "guide"},
        "rooms": _room_map(
            {
                "camp": {"exits": {"north": "ending"}, "npcs": ["guide"]},
                "ending": {},
            }
        ),
    },
    "platformer": {
        "core_loop": ["run", "jump", "collect"],
        "verbs": ["move", "jump", "pickup"],
        "start_room": "start",
        "win": {"room": "ledge", "has_item": "coin"},
        "rooms": _room_map(
            {
                "start": {"exits": {"up": "ledge"}},
                "ledge": {"items": ["coin"]},
            }
        ),
    },
    "adventure": {
        "core_loop": ["explore", "act", "resolve"],
        "verbs": ["move", "pickup"],
        "start_room": "clearing",
        "win": {"room": "shrine", "has_item": "map"},
        "rooms": _room_map(
            {
                "clearing": {"exits": {"north": "shrine"}, "items": ["map"]},
                "shrine": {"exits": {"south": "clearing"}},
            }
        ),
    },
}
