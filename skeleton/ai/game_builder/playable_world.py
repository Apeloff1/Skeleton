"""Deterministic, original, solvable multi-level grid worlds for the game builder.

Unlike a decorative plan, this module constructs an actual game map and solves
its collectible-and-exit puzzle before allowing delivery. It never incorporates
the expressive content of a reviewed third-party source.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import random
import re
from typing import Iterable

from .contracts import canonical_digest

MAX_LEVELS = 8
MAX_DIMENSION = 41
MAX_COLLECTIBLES = 6
MAX_HAZARDS = 24
DIRECTIONS = (
    ("up", 0, -1), ("left", -1, 0),
    ("right", 1, 0), ("down", 0, 1),
)
_ALLOWED_TILES = frozenset("#.SGCH")
_THEMES = frozenset({"forest", "space", "desert", "ocean", "arcade"})


class PlayableWorldError(ValueError):
    """Unsatisfiable or invalid executable game world."""


def _int(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise PlayableWorldError(f"invalid {name}")
    return value


def _word(value: object, name: str, maximum: int) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or value != value.strip() or not value
            or any(ord(c) < 32 for c in value)):
        raise PlayableWorldError(f"invalid {name}")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise PlayableWorldError(f"invalid Unicode in {name}") from exc
    return value


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise PlayableWorldError(f"invalid {name}")
    return value


@dataclass(frozen=True, slots=True)
class GameBuildIntent:
    project_id: str
    title: str
    subtitle: str
    seed: int
    width: int = 19
    height: int = 15
    levels: int = 3
    collectibles_per_level: int = 3
    hazards_per_level: int = 5
    theme: str = "forest"
    starting_health: int = 3

    def __post_init__(self) -> None:
        _id(self.project_id, "project_id")
        _word(self.title, "title", 120)
        _word(self.subtitle, "subtitle", 400)
        _int(self.seed, "seed", 0, 2**63 - 1)
        _int(self.width, "width", 9, MAX_DIMENSION)
        _int(self.height, "height", 9, MAX_DIMENSION)
        if self.width % 2 != 1 or self.height % 2 != 1:
            raise PlayableWorldError("maze dimensions must be odd")
        _int(self.levels, "levels", 1, MAX_LEVELS)
        _int(self.collectibles_per_level, "collectibles_per_level", 1, MAX_COLLECTIBLES)
        _int(self.hazards_per_level, "hazards_per_level", 0, MAX_HAZARDS)
        _int(self.starting_health, "starting_health", 1, 10)
        if self.theme not in _THEMES:
            raise PlayableWorldError("unsupported game theme")

    def to_payload(self) -> dict[str, object]:
        return {
            "project_id": self.project_id, "title": self.title,
            "subtitle": self.subtitle, "seed": self.seed,
            "width": self.width, "height": self.height,
            "levels": self.levels, "collectibles_per_level": self.collectibles_per_level,
            "hazards_per_level": self.hazards_per_level,
            "theme": self.theme, "starting_health": self.starting_health,
        }


@dataclass(frozen=True, slots=True)
class TileLevel:
    index: int
    rows: tuple[str, ...]
    start: tuple[int, int]
    exit: tuple[int, int]
    collectibles: tuple[tuple[int, int], ...]
    hazards: tuple[tuple[int, int], ...]
    safe_solution: tuple[str, ...]

    def __post_init__(self) -> None:
        _int(self.index, "level index", 0, MAX_LEVELS - 1)
        if not isinstance(self.rows, tuple) or not 9 <= len(self.rows) <= MAX_DIMENSION:
            raise PlayableWorldError("invalid level rows")
        width = len(self.rows[0])
        if width < 9 or width > MAX_DIMENSION or width % 2 == 0 or len(self.rows) % 2 == 0:
            raise PlayableWorldError("invalid level dimensions")
        if any(not isinstance(row, str) or len(row) != width
               or set(row) - _ALLOWED_TILES for row in self.rows):
            raise PlayableWorldError("invalid level tile data")
        if any(row[0] != "#" or row[-1] != "#" for row in self.rows):
            raise PlayableWorldError("level border must be solid")
        if set(self.rows[0]) != {"#"} or set(self.rows[-1]) != {"#"}:
            raise PlayableWorldError("level top and bottom must be sealed")
        locations: dict[str, list[tuple[int, int]]] = {}
        for y, row in enumerate(self.rows):
            for x, tile in enumerate(row):
                locations.setdefault(tile, []).append((x, y))
        if (
            locations.get("S") != [self.start]
            or locations.get("G") != [self.exit]
            or tuple(sorted(locations.get("C", []))) != self.collectibles
            or tuple(sorted(locations.get("H", []))) != self.hazards
        ):
            raise PlayableWorldError("level tile markers and references mismatch")
        if not 1 <= len(self.collectibles) <= MAX_COLLECTIBLES:
            raise PlayableWorldError("a level must offer collectible objectives")
        if len(self.hazards) > MAX_HAZARDS:
            raise PlayableWorldError("too many hazards")
        if (
            not isinstance(self.safe_solution, tuple)
            or not self.safe_solution
            or len(self.safe_solution) > 20000
            or any(action not in {name for name, _, _ in DIRECTIONS}
                   for action in self.safe_solution)
        ):
            raise PlayableWorldError("safe solution must contain bounded playable moves")
        if solve_safe_path(self.rows) != self.safe_solution:
            raise PlayableWorldError("level solution does not reproduce")

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "index": self.index, "rows": list(self.rows),
            "start": list(self.start), "exit": list(self.exit),
            "collectibles": [list(p) for p in self.collectibles],
            "hazards": [list(p) for p in self.hazards],
            "solution_steps": len(self.safe_solution),
            "solution_digest": canonical_digest(list(self.safe_solution)),
        }


@dataclass(frozen=True, slots=True)
class PlayableWorld:
    intent: GameBuildIntent
    levels: tuple[TileLevel, ...]
    algorithm: str = "skeleton.game_builder.maze-puzzle.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.intent, GameBuildIntent):
            raise PlayableWorldError("GameBuildIntent required")
        if not isinstance(self.levels, tuple) or len(self.levels) != self.intent.levels:
            raise PlayableWorldError("level count mismatch")
        if any(not isinstance(level, TileLevel) or level.index != i
               or level.width != self.intent.width
               or level.height != self.intent.height
               or len(level.collectibles) != self.intent.collectibles_per_level
               for i, level in enumerate(self.levels)):
            raise PlayableWorldError("generated level shape mismatch")
        if self.algorithm != "skeleton.game_builder.maze-puzzle.v1":
            raise PlayableWorldError("unrecognized world algorithm")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.playable_world.v1",
            "algorithm": self.algorithm,
            "intent": self.intent.to_payload(),
            "levels": [level.to_payload() for level in self.levels],
        }


def _neighbors(point: tuple[int, int], width: int, height: int) -> Iterable[tuple[int, int]]:
    x, y = point
    for _, dx, dy in DIRECTIONS:
        xx, yy = x + dx, y + dy
        if 0 <= xx < width and 0 <= yy < height:
            yield xx, yy


def _walk_distances(
    rows: tuple[str, ...] | list[str],
    origin: tuple[int, int],
) -> dict[tuple[int, int], int]:
    distance = {origin: 0}
    pending = deque([origin])
    while pending:
        current = pending.popleft()
        for nxt in _neighbors(current, len(rows[0]), len(rows)):
            if nxt in distance or rows[nxt[1]][nxt[0]] == "#":
                continue
            distance[nxt] = distance[current] + 1
            pending.append(nxt)
    return distance


def _simple_path(
    rows: list[str], start: tuple[int, int], dest: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == dest:
            break
        for nxt in _neighbors(cur, len(rows[0]), len(rows)):
            if nxt not in parents and rows[nxt[1]][nxt[0]] != "#":
                parents[nxt] = cur
                queue.append(nxt)
    if dest not in parents:
        raise PlayableWorldError("unreachable generated point")
    path = []
    cur: tuple[int, int] | None = dest
    while cur is not None:
        path.append(cur)
        cur = parents[cur]
    return tuple(reversed(path))


def solve_safe_path(rows: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """BFS in (x, y, collected-bitmask); H is impassable for safe route proof.

    The bound is 41*41*2^6 states, not an exponential traversal of arbitrary
    source content; objective markers are capped by GameBuildIntent.
    """
    if not rows or len(rows) > MAX_DIMENSION or any(
        not isinstance(row, str) or len(row) != len(rows[0]) for row in rows
    ):
        raise PlayableWorldError("invalid pathfinding grid")
    starts = [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "S"]
    goals = [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "G"]
    collectibles = sorted((x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "C")
    if len(starts) != 1 or len(goals) != 1 or not 1 <= len(collectibles) <= MAX_COLLECTIBLES:
        raise PlayableWorldError("invalid solver objectives")
    item_bits = {p: 1 << i for i, p in enumerate(collectibles)}
    all_items = (1 << len(collectibles)) - 1
    origin = (*starts[0], 0)
    queue = deque([origin])
    came: dict[tuple[int, int, int], tuple[tuple[int, int, int], str] | None] = {
        origin: None,
    }
    terminal = None
    while queue:
        x, y, mask = queue.popleft()
        if (x, y) == goals[0] and mask == all_items:
            terminal = (x, y, mask)
            break
        for name, dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if ny < 0 or ny >= len(rows) or nx < 0 or nx >= len(rows[0]):
                continue
            tile = rows[ny][nx]
            if tile in "#H":
                continue
            state = (nx, ny, mask | item_bits.get((nx, ny), 0))
            if state in came:
                continue
            came[state] = ((x, y, mask), name)
            queue.append(state)
        if len(came) > MAX_DIMENSION * MAX_DIMENSION * (1 << MAX_COLLECTIBLES):
            raise PlayableWorldError("pathfinding state budget exceeded")
    if terminal is None:
        raise PlayableWorldError("generated map lacks hazard-free collectible exit route")
    actions: list[str] = []
    current = terminal
    while came[current] is not None:
        parent, direction = came[current]
        actions.append(direction)
        current = parent
    actions.reverse()
    return tuple(actions)


def _maze(width: int, height: int, rng: random.Random) -> list[list[str]]:
    grid = [["#" for _ in range(width)] for _ in range(height)]
    start = (1, 1)
    grid[1][1] = "."
    stack = [start]
    directions = [(0, -2), (-2, 0), (2, 0), (0, 2)]
    while stack:
        x, y = stack[-1]
        options = []
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 1 <= nx < width - 1 and 1 <= ny < height - 1 and grid[ny][nx] == "#":
                options.append((nx, ny, dx, dy))
        if not options:
            stack.pop()
            continue
        nx, ny, dx, dy = rng.choice(options)
        grid[y + dy // 2][x + dx // 2] = "."
        grid[ny][nx] = "."
        stack.append((nx, ny))
    return grid


def _build_level(intent: GameBuildIntent, index: int) -> TileLevel:
    mix = canonical_digest({
        "generator": "skeleton.game_builder.maze-puzzle.v1",
        "project_id": intent.project_id,
        "seed": intent.seed,
        "index": index,
    })
    rng = random.Random(int(mix[:16], 16))
    grid = _maze(intent.width, intent.height, rng)
    rows = ["".join(row) for row in grid]
    start = (1, 1)
    distance = _walk_distances(rows, start)
    candidates = [p for p in distance if p != start and distance[p] >= 3]
    if len(candidates) < intent.collectibles_per_level + 1:
        raise PlayableWorldError("not enough generated objective positions")
    goal = max(candidates, key=lambda p: (distance[p], p[1], p[0]))
    candidates.remove(goal)
    # Disperse objectives across corridors without overrunning the exits.
    rng.shuffle(candidates)
    candidates.sort(key=lambda p: -distance[p])
    items: list[tuple[int, int]] = []
    for pos in candidates:
        if all(abs(pos[0] - x) + abs(pos[1] - y) > 2 for x, y in items):
            items.append(pos)
        if len(items) == intent.collectibles_per_level:
            break
    if len(items) != intent.collectibles_per_level:
        items = candidates[:intent.collectibles_per_level]
    itemset = set(items)
    # Preserve all chosen minimal routes. Optional hazards never block the
    # demonstration safe path, including intermediate collectibles.
    protected = {start, goal, *items}
    for point in (*items, goal):
        protected.update(_simple_path(rows, start, point))
    hazard_candidates = [p for p in distance
                         if p not in protected and distance[p] > 3]
    rng.shuffle(hazard_candidates)
    hazards = tuple(sorted(hazard_candidates[:intent.hazards_per_level]))
    grid[start[1]][start[0]] = "S"
    grid[goal[1]][goal[0]] = "G"
    for x, y in items:
        grid[y][x] = "C"
    for x, y in hazards:
        grid[y][x] = "H"
    result = tuple("".join(row) for row in grid)
    proof = solve_safe_path(result)
    return TileLevel(
        index, result, start, goal, tuple(sorted(itemset)), hazards, proof,
    )


def generate_playable_world(intent: GameBuildIntent, *, authorized: bool) -> PlayableWorld:
    if not authorized:
        raise PermissionError("game world generation requires authorization")
    if not isinstance(intent, GameBuildIntent):
        raise PlayableWorldError("typed GameBuildIntent required")
    world = PlayableWorld(
        intent, tuple(_build_level(intent, index) for index in range(intent.levels)),
    )
    # The digest is over an internally consistent, safely navigable geometry.
    world.digest
    return world


__all__ = [
    "GameBuildIntent", "PlayableWorld", "PlayableWorldError",
    "TileLevel", "generate_playable_world", "solve_safe_path", "DIRECTIONS",
]
