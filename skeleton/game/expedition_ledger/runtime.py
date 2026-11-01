"""Deterministic, source-bound, playable expedition ledger.

Trusted game package data only. No network, plugins, untrusted code execution,
nondeterministic clocks, hidden global state, or inferred platform qualification.
The receipt is a replay/integrity commitment, NOT a cryptographic signature.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections import deque
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "skeleton.game.expedition_ledger.v1"
SAVE_SCHEMA = "skeleton.game.expedition_save.v1"
MAX_TURNS = 256
MAX_SEARCH = 16000
MAX_CONTRACT_BYTES = 65536
THEMES = (
    "ashen_delta", "clockwork_sanctuary", "saltglass_cavern",
    "ember_orchard", "moonlit_breakwater", "copper_tundra", "verdant_ruins",
)
DISCIPLINES = (
    "cartographer", "diplomat", "machinist", "herbalist",
    "sentinel", "historian", "navigator",
)
CHAPTER_IDS = tuple(
    f"{theme}__{discipline}" for theme in THEMES for discipline in DISCIPLINES
)
MOVES: dict[str, tuple[int, int]] = {
    "north": (0, -1), "south": (0, 1),
    "west": (-1, 0), "east": (1, 0),
}
TILES = frozenset("#.SKHOREC?XMFL")


class ExpeditionError(ValueError):
    """Invalid contract, move, transition, replay, or save-state evidence."""


@dataclass(frozen=True)
class Episode:
    chapter_id: str
    layout: dict[str, Any]
    quest: dict[str, Any]
    encounters: dict[str, Any]
    source_digest: str

    @property
    def rows(self) -> tuple[str, ...]:
        return tuple(self.layout["rows"])


@dataclass(frozen=True)
class State:
    chapter_id: str
    source_digest: str
    x: int
    y: int
    health: int
    energy: int
    has_key: bool
    objective: bool
    reputation: int
    score: int
    turns: int
    visited: tuple[str, ...]
    events: tuple[str, ...]
    commands: tuple[str, ...]
    status: str


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _trusted_document(path: Path) -> dict[str, Any]:
    # Files are shipped as trusted package source. Do not use this loader for
    # user-supplied ZIPs or uploaded packages (use asset_ingest there).
    if not path.is_file() or path.stat().st_size > MAX_CONTRACT_BYTES:
        raise ExpeditionError("episode contract missing or exceeds byte cap")
    payload = path.read_bytes()
    if len(payload) > MAX_CONTRACT_BYTES:
        raise ExpeditionError("episode contract exceeded byte cap")
    try:
        value = json.loads(payload)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ExpeditionError("episode contract is not valid JSON") from exc
    if type(value) is not dict:
        raise ExpeditionError("episode contract must be an object")
    return value


def load_episode(chapter_id: str) -> Episode:
    if type(chapter_id) is not str or chapter_id not in CHAPTER_IDS:
        raise ExpeditionError("chapter identifier outside published catalog")
    root = Path(__file__).parent / "chapters" / chapter_id
    layout = _trusted_document(root / "layout.json")
    quest = _trusted_document(root / "quest.json")
    encounters = _trusted_document(root / "encounters.json")
    if any(doc.get("id") != chapter_id for doc in (layout, quest, encounters)):
        raise ExpeditionError("chapter contract identity mismatch")
    if layout.get("schema") != SCHEMA or quest.get("schema") != SCHEMA:
        raise ExpeditionError("chapter contract schema mismatch")
    if encounters.get("schema") != SCHEMA:
        raise ExpeditionError("encounter contract schema mismatch")
    rows = layout.get("rows")
    if (type(rows) is not list or len(rows) < 5 or len(rows) > 32
            or any(type(row) is not str for row in rows)):
        raise ExpeditionError("invalid bounded episode grid")
    width = len(rows[0])
    if width < 5 or width > 32 or any(len(row) != width for row in rows):
        raise ExpeditionError("episode grid is ragged or oversized")
    if any(set(row) - TILES for row in rows):
        raise ExpeditionError("episode contains unknown tile")
    for symbol in "SKOE":
        if sum(row.count(symbol) for row in rows) != 1:
            raise ExpeditionError(f"episode requires one {symbol} tile")
    if any(row[0] != "#" or row[-1] != "#" for row in rows):
        raise ExpeditionError("episode side walls must be closed")
    if rows[0] != "#" * width or rows[-1] != "#" * width:
        raise ExpeditionError("episode top and bottom walls must be closed")
    if quest.get("theme") not in THEMES:
        raise ExpeditionError("episode theme not in catalog")
    if quest.get("discipline") not in DISCIPLINES:
        raise ExpeditionError("episode discipline not in catalog")
    if chapter_id != f"{quest['theme']}__{quest['discipline']}":
        raise ExpeditionError("episode chapter/quest provenance mismatch")
    if any(type(quest.get(key)) is not str or not quest[key] for key in (
        "title", "premise", "objective_name", "key_name", "ending",
        "faction", "challenge", "choice_yes", "choice_no",
    )):
        raise ExpeditionError("missing authored quest requirements")
    for key in ("hazard_damage", "guardian_damage", "recharge", "supply",
                "medicine", "faction_reputation", "choice_reputation",
                "lore_score"):
        value = encounters.get(key)
        if type(value) is not int or not 0 <= value <= 12:
            raise ExpeditionError(f"encounter {key} outside bounded range")
    source = digest(
        {"layout": layout, "quest": quest, "encounters": encounters}
    )
    return Episode(chapter_id, layout, quest, encounters, source)


def _spawn(ep: Episode) -> tuple[int, int]:
    for y, row in enumerate(ep.rows):
        x = row.find("S")
        if x >= 0:
            return x, y
    raise ExpeditionError("missing start tile")


def new_game(ep: Episode) -> State:
    x, y = _spawn(ep)
    return State(
        ep.chapter_id, ep.source_digest, x, y,
        health=12, energy=20, has_key=False, objective=False,
        reputation=0, score=0, turns=0, visited=(f"{x},{y}",),
        events=("expedition_started",), commands=(), status="active",
    )


def _require_state(ep: Episode, state: State) -> None:
    if not isinstance(state, State):
        raise ExpeditionError("state must be typed")
    if state.chapter_id != ep.chapter_id or not hmac.compare_digest(
        state.source_digest, ep.source_digest
    ):
        raise ExpeditionError("state cannot be rebound to another source")
    if state.status not in ("active", "won", "lost"):
        raise ExpeditionError("unknown expedition status")
    if not (0 <= state.x < len(ep.rows[0]) and 0 <= state.y < len(ep.rows)):
        raise ExpeditionError("state outside episode grid")
    if ep.rows[state.y][state.x] == "#":
        raise ExpeditionError("state occupies a wall")
    if (type(state.turns) is not int or not 0 <= state.turns <= MAX_TURNS
            or type(state.health) is not int or not 0 <= state.health <= 12
            or type(state.energy) is not int or not 0 <= state.energy <= 32
            or len(state.commands) != state.turns):
        raise ExpeditionError("state bounds or command ledger inconsistent")


def step(ep: Episode, state: State, direction: str) -> State:
    _require_state(ep, state)
    if type(direction) is not str or direction not in MOVES:
        raise ExpeditionError("unsupported movement command")
    if state.status != "active":
        raise ExpeditionError("cannot mutate a terminal expedition")
    if state.turns >= MAX_TURNS:
        raise ExpeditionError("expedition turn limit reached")
    dx, dy = MOVES[direction]
    x, y = state.x + dx, state.y + dy
    if not (0 <= x < len(ep.rows[0]) and 0 <= y < len(ep.rows)):
        raise ExpeditionError("movement exceeds closed grid")
    tile = ep.rows[y][x]
    events = list(state.events)
    visited = list(state.visited)
    energy = max(0, state.energy - 1)
    health, score = state.health, state.score
    reputation = state.reputation
    has_key, objective, status = state.has_key, state.objective, "active"
    if tile == "#":
        events.append("wall_blocked")
        x, y = state.x, state.y
    else:
        location = f"{x},{y}"
        first_visit = location not in visited
        if first_visit:
            visited.append(location)
            effects = ep.encounters
            if tile == "K":
                has_key = True
                events.append("source_key_collected")
                score += 5
            elif tile == "O":
                if has_key:
                    objective = True
                    events.append("objective_recovered")
                    score += 20
                else:
                    events.append("objective_locked")
            elif tile == "H":
                health = max(0, health - effects["hazard_damage"])
                events.append("environmental_hazard")
            elif tile == "X":
                health = max(0, health - effects["guardian_damage"])
                events.append("guardian_encounter")
            elif tile == "R":
                energy = min(32, energy + effects["recharge"])
                events.append("field_recharge")
            elif tile == "C":
                energy = min(32, energy + effects["supply"])
                events.append("supply_recovery")
            elif tile == "M":
                health = min(12, health + effects["medicine"])
                events.append("field_medicine")
            elif tile == "F":
                reputation += effects["faction_reputation"]
                events.append("faction_contact")
            elif tile == "?":
                reputation += effects["choice_reputation"]
                events.append("dialogue_choice_resolved")
            elif tile == "L":
                score += effects["lore_score"]
                events.append("lore_discovered")
        # A first visit to a locked objective must not permanently consume
        # the pickup. Revisiting after recovering the source key is legal,
        # while the score and recovery event remain strictly one-shot.
        if tile == "O" and has_key and not objective:
            objective = True
            events.append("objective_recovered")
            score += 20
        if tile == "E":
            if objective:
                status = "won"
                events.append("expedition_completed")
                score += 40 + max(0, health)
            else:
                events.append("exit_requires_objective")
    if health <= 0 or energy <= 0:
        status = "lost"
        events.append("expedition_resources_exhausted")
    result = replace(
        state, x=x, y=y, health=health, energy=energy,
        has_key=has_key, objective=objective, reputation=reputation,
        score=score, turns=state.turns + 1, visited=tuple(visited),
        events=tuple(events), commands=state.commands + (direction,),
        status=status,
    )
    _require_state(ep, result)
    return result


def run_episode(ep: Episode, commands: Iterable[str]) -> State:
    current = new_game(ep)
    for index, direction in enumerate(commands):
        if index >= MAX_TURNS:
            raise ExpeditionError("input commands exceed turn cap")
        current = step(ep, current, direction)
    return current


def snapshot(ep: Episode, state: State) -> dict[str, Any]:
    """Canonical integrity receipt for a reachable deterministic state."""
    _require_state(ep, state)
    body = json.loads(canonical(asdict(state)))
    # Verify that a supplied state is reachable, not simply well-formed.
    if json.loads(canonical(asdict(run_episode(ep, state.commands)))) != body:
        raise ExpeditionError("state does not match deterministic replay")
    return {"schema": SAVE_SCHEMA, "state": body, "digest": digest(body)}


def restore(ep: Episode, envelope: dict[str, Any]) -> State:
    """Reject a stale source, forged transition, or noncanonical save."""
    if type(envelope) is not dict or set(envelope) != {
        "schema", "state", "digest",
    } or envelope["schema"] != SAVE_SCHEMA:
        raise ExpeditionError("invalid save envelope")
    body = envelope["state"]
    if type(body) is not dict or type(envelope["digest"]) is not str:
        raise ExpeditionError("invalid save state body")
    if not hmac.compare_digest(envelope["digest"], digest(body)):
        raise ExpeditionError("save digest mismatch")
    commands = body.get("commands")
    if (type(commands) is not list or len(commands) > MAX_TURNS
            or any(type(command) is not str or command not in MOVES
                   for command in commands)):
        raise ExpeditionError("invalid bounded save command history")
    state = run_episode(ep, commands)
    if json.loads(canonical(asdict(state))) != body:
        raise ExpeditionError("save state conflicts with verified replay")
    return state


def shortest_plan(ep: Episode) -> tuple[str, ...]:
    """Bounded breadth-first solution of the actual state transitions."""
    start = new_game(ep)
    queue = deque([(start, ())])
    visited: set[tuple[Any, ...]] = set()
    while queue and len(visited) < MAX_SEARCH:
        current, path = queue.popleft()
        signature = (
            current.x, current.y, current.has_key, current.objective,
            current.health, current.energy,
        )
        if signature in visited:
            continue
        visited.add(signature)
        if current.status == "won":
            return path
        if current.status != "active" or len(path) >= 48:
            continue
        for direction in ("east", "north", "south", "west"):
            next_state = step(ep, current, direction)
            if next_state.status != "lost":
                queue.append((next_state, path + (direction,)))
    raise ExpeditionError("no bounded winning path in episode")


def evidence(ep: Episode, state: State) -> dict[str, Any]:
    receipt = snapshot(ep, state)
    return {
        "chapter_id": ep.chapter_id,
        "source_digest": ep.source_digest,
        "command_digest": digest(list(state.commands)),
        "state_digest": receipt["digest"],
        "status": state.status,
        "turns": state.turns,
        "score": state.score,
        "integrity_only": True,
    }
