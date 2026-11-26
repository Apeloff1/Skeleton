"""Playable Godot 4 export: questionnaire answers -> a game you can actually play.

``godot_emit`` materialises the forge's era pack as a bootable project; the
playtest gate (:mod:`skeleton.forge.playtest`) proves it boots. This module
goes further and emits a *playable* game: a generated level scene, a real
player controller (move / dodge with i-frames / gun, melee or tool), tiered
enemy AI on a flow field, a HUD, and one complete **core loop per archetype**
with win and lose states:

========== ==============================================================
loop       core loop
========== ==============================================================
extraction grab data cores, manage weapon heat, beat the collapse clock, exfil
arena      survive escalating portal waves, combo scoring, continue credits
soulslike  stamina melee, telegraphed strikes, shrines, echoes, 2-phase boss
cozy       plant/harvest/sell, day clock, festival coin goal, no combat
horror     failing flashlight, scarce ammo, noise aggro, key + locked exit
========== ==============================================================

Every numeric rule is derived from the forged era pack (player speed/health,
i-frames, heat model, recipe damage/rpm, TTK targets, collapse clock) so the
questionnaire materially changes the game. All art/audio is procedural
placeholder, clearly labelled in-game and in ``data/asset_manifest.json``.

Each project ships a deterministic ``Autopilot`` so a headless run can prove
the loop is *completable*, not just bootable::

    godot --headless --path OUT --fixed-fps 60 -- --autoplay --smoke-seconds=300

which prints ``FORGE_SMOKE {json}`` and exits 0 on a win. :func:`smoke_run`
drives that and reuses the playtest gate's binary resolution and log scan.

CLI::

    python -m skeleton.forge.playable --answers answers.json --out build/game [--smoke]
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

GODOT_VERSION = "4.3"
SCHEMA = "skeleton.forge.playable/v1"
SMOKE_SCHEMA = "skeleton.forge.playable.smoke/v1"
TEMPLATE_DIR = Path(__file__).resolve().parent / "playable_templates"

LOOPS: Tuple[str, ...] = ("extraction", "arena", "soulslike", "cozy", "horror")
LOOP_LABELS: Dict[str, str] = {
    "extraction": "Extraction Run",
    "arena": "Arena Survival",
    "soulslike": "Soulslike Descent",
    "cozy": "Cozy Season",
    "horror": "Survival Horror",
}

# Best-fit playable loop for every canonical era (forge.eras.list_eras()).
ERA_LOOPS: Dict[str, str] = {
    "extraction_now": "extraction", "roguelike": "extraction", "battle_royale": "extraction",
    "boomer_shooter": "arena", "arcade_golden_age": "arena", "bullet_heaven": "arena",
    "fighting_game": "arena", "modern_aaa": "arena", "tactics_grid": "arena",
    "soulslike": "soulslike", "metroidvania": "soulslike", "jrpg": "soulslike",
    "crpg": "soulslike", "mmorpg": "soulslike",
    "cozy_wholesome": "cozy", "city_builder": "cozy", "grand_strategy": "cozy",
    "visual_novel": "cozy", "walking_sim": "cozy", "deckbuilder": "cozy",
    "indie_experimental": "cozy",
    "horror_survival": "horror", "stealth": "horror", "immersive_sim": "horror",
}

# Genre words that override the era vote (checked as substrings, in order).
GENRE_LOOPS: Tuple[Tuple[str, str], ...] = (
    ("extraction", "extraction"), ("roguel", "extraction"), ("heist", "extraction"),
    ("horror", "horror"), ("stealth", "horror"), ("survival-horror", "horror"),
    ("souls", "soulslike"), ("arpg", "soulslike"), ("rpg", "soulslike"), ("metroid", "soulslike"),
    ("action-adventure", "soulslike"),
    ("shooter", "arena"), ("fps", "arena"), ("arcade", "arena"), ("bullet", "arena"),
    ("fighting", "arena"), ("twin-stick", "arena"),
    ("cozy", "cozy"), ("farm", "cozy"), ("life-sim", "cozy"), ("simulation", "cozy"),
    ("city-builder", "cozy"), ("narrative", "cozy"), ("visual-novel", "cozy"),
)


class PlayableExportError(ValueError):
    """Raised when answers/pack cannot produce a playable project."""


def _tmpl(name: str) -> str:
    return (TEMPLATE_DIR / f"{name}.tmpl").read_text(encoding="utf-8")


def _fill(text: str, tokens: Mapping[str, Any]) -> str:
    for key, value in tokens.items():
        text = text.replace(f"__{key}__", str(value))
    leftover = re.findall(r"__[A-Z][A-Z0-9_]*__", text)
    if leftover:
        raise PlayableExportError(f"unfilled template tokens: {sorted(set(leftover))}")
    return text


# ---------------------------------------------------------------------------
# Loop choice
# ---------------------------------------------------------------------------

def choose_loop(era: str, answers: Optional[Mapping[str, Any]] = None) -> Tuple[str, str]:
    """Return ``(loop, reason)``.

    Priority: explicit ``loop``/``archetype`` answer > ``combat=none`` (cozy)
    > genre keyword > era best-fit > ``extraction``.
    """
    answers = answers or {}
    for key in ("loop", "archetype", "game_loop"):
        raw = answers.get(key)
        if isinstance(raw, str) and raw.strip().lower() in LOOPS:
            return raw.strip().lower(), f"explicit {key}"
    combat = str(answers.get("combat") or "").strip().lower()
    if combat in {"none", "no", "pacifist"}:
        return "cozy", "combat=none"
    genre = str(answers.get("genre") or "").strip().lower().replace(" ", "-")
    if genre:
        for needle, loop in GENRE_LOOPS:
            if needle in genre:
                return loop, f"genre~{needle}"
    if era in ERA_LOOPS:
        return ERA_LOOPS[era], f"era={era}"
    return "extraction", "default"


# ---------------------------------------------------------------------------
# Level generation (deterministic, connectivity-checked)
# ---------------------------------------------------------------------------

Grid = List[List[str]]
Room = Tuple[int, int, int, int]  # x, y, w, h (interior)


def _blank(w: int, h: int) -> Grid:
    return [["#"] * w for _ in range(h)]


def _carve_rect(g: Grid, x: int, y: int, w: int, h: int) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            g[yy][xx] = "."


def _carve_corridor(g: Grid, a: Tuple[int, int], b: Tuple[int, int], width: int, rng: random.Random) -> None:
    (x1, y1), (x2, y2) = a, b
    horizontal_first = rng.random() < 0.5
    pts = [(x1, y1), (x2, y1), (x2, y2)] if horizontal_first else [(x1, y1), (x1, y2), (x2, y2)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        for xx in range(min(ax, bx), max(ax, bx) + width):
            for yy in range(min(ay, by), max(ay, by) + width):
                if 0 < yy < len(g) - 1 and 0 < xx < len(g[0]) - 1:
                    g[yy][xx] = "."


def _rooms_level(rng: random.Random, w: int, h: int, n: int, size: Tuple[int, int],
                 corridor: int, last_big: bool = False) -> Tuple[Grid, List[Room]]:
    g = _blank(w, h)
    rooms: List[Room] = []
    tries = 0
    while len(rooms) < n and tries < 2000:
        tries += 1
        big = last_big and len(rooms) == n - 1
        rw = rng.randint(size[1], size[1] + 4) if big else rng.randint(size[0], size[1])
        rh = rng.randint(size[1] - 1, size[1] + 2) if big else rng.randint(size[0], size[1] - 1)
        x = rng.randint(2, w - rw - 3)
        y = rng.randint(2, h - rh - 3)
        if any(x < ox + ow + 3 and ox < x + rw + 3 and y < oy + oh + 3 and oy < y + rh + 3
               for ox, oy, ow, oh in rooms):
            continue
        rooms.append((x, y, rw, rh))
    if len(rooms) < max(3, n // 2):
        raise PlayableExportError("level generator could not place enough rooms")
    rooms.sort(key=lambda r: (r[0] + r[2] / 2.0, r[1]))
    for r in rooms:
        _carve_rect(g, *r)
    for a, b in zip(rooms, rooms[1:]):
        ca = (a[0] + a[2] // 2, a[1] + a[3] // 2)
        cb = (b[0] + b[2] // 2, b[1] + b[3] // 2)
        _carve_corridor(g, ca, cb, corridor, rng)
    return g, rooms


def _free_in(g: Grid, room: Room, rng: random.Random, margin: int = 1) -> Optional[Tuple[int, int]]:
    x, y, w, h = room
    cells = [(xx, yy) for yy in range(y + margin, y + h - margin) for xx in range(x + margin, x + w - margin)
             if g[yy][xx] == "."]
    return rng.choice(cells) if cells else None


def _place(g: Grid, room: Room, ch: str, rng: random.Random, margin: int = 1) -> Optional[Tuple[int, int]]:
    cell = _free_in(g, room, rng, margin) or _free_in(g, room, rng, 0)
    if cell:
        g[cell[1]][cell[0]] = ch
    return cell


def _bfs(g: Grid, start: Tuple[int, int]) -> Dict[Tuple[int, int], int]:
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= ny < len(g) and 0 <= nx < len(g[0]) and g[ny][nx] != "#" and (nx, ny) not in dist:
                dist[(nx, ny)] = dist[(x, y)] + 1
                q.append((nx, ny))
    return dist


def _room_center(r: Room) -> Tuple[int, int]:
    return r[0] + r[2] // 2, r[1] + r[3] // 2


def _find(g: Grid, ch: str) -> List[Tuple[int, int]]:
    return [(x, y) for y, row in enumerate(g) for x, c in enumerate(row) if c == ch]


def _level_extraction(rng: random.Random, p: Dict[str, Any]) -> Grid:
    g, rooms = _rooms_level(rng, 60, 40, 9, (6, 10), 2)
    start = rooms[0]
    _place(g, start, "P", rng)
    d = _bfs(g, _room_center(start))
    ordered = sorted(rooms[1:], key=lambda r: d.get(_room_center(r), 0))
    exit_room = ordered[-1]
    _place(g, exit_room, "X", rng)
    loot_rooms = ordered[:-1]
    rng.shuffle(loot_rooms)
    for r in loot_rooms[: p["cores_total"]]:
        _place(g, r, "C", rng)
    for i, r in enumerate(ordered):
        for _ in range(2 if i < len(ordered) // 2 else 3):
            _place(g, r, "E", rng)
        if i % 3 == 2:
            _place(g, r, "L", rng)
    for r in loot_rooms[-2:]:
        cell = _free_in(g, r, rng, 2)
        if cell:
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                if g[cell[1] + dy][cell[0] + dx] == ".":
                    g[cell[1] + dy][cell[0] + dx] = "H"
    for r in ordered[1::3]:
        _place(g, r, "M", rng)
    return g


def _level_arena(rng: random.Random, p: Dict[str, Any]) -> Grid:
    w, h = 42, 28
    g = _blank(w, h)
    _carve_rect(g, 1, 1, w - 2, h - 2)
    cx, cy = w // 2, h // 2
    placed = 0
    while placed < 9:
        x, y = rng.randint(4, w - 7), rng.randint(4, h - 7)
        if abs(x - cx) < 6 and abs(y - cy) < 5:
            continue
        if any(g[yy][xx] == "#" for yy in range(y - 2, y + 4) for xx in range(x - 2, x + 4)):
            continue
        for yy in range(y, y + 2):
            for xx in range(x, x + 2):
                g[yy][xx] = "#"
        placed += 1
    g[cy][cx] = "P"
    for (x, y) in ((3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4), (cx, 2), (cx, h - 3)):
        g[y][x] = "O"
    return g


def _level_soulslike(rng: random.Random, p: Dict[str, Any]) -> Grid:
    g, rooms = _rooms_level(rng, 58, 38, 6, (6, 9), 2, last_big=True)
    boss_room = max(rooms[1:], key=lambda r: r[2] * r[3])
    others = [r for r in rooms if r is not boss_room]
    start = others[0]
    _place(g, start, "P", rng)
    sx, sy = _room_center(start)
    g[sy - 1 if g[sy - 1][sx] == "." else sy][sx] = "S"
    d = _bfs(g, _find(g, "P")[0])
    mids = sorted(others[1:], key=lambda r: d.get(_room_center(r), 0))
    if mids:
        near_boss = mids[-1]
        _place(g, near_boss, "S", rng)
    for i, r in enumerate(mids):
        _place(g, r, "E", rng)
        _place(g, r, "E", rng)
        if i % 2 == 1:
            _place(g, r, "L", rng)
    bx, by = _room_center(boss_room)
    g[by][bx] = "B"
    far = max(((x, y) for y in range(boss_room[1] + 1, boss_room[1] + boss_room[3] - 1)
               for x in range(boss_room[0] + 1, boss_room[0] + boss_room[2] - 1) if g[y][x] == "."),
              key=lambda c: d.get(c, 0))
    g[far[1]][far[0]] = "X"
    return g


def _level_cozy(rng: random.Random, p: Dict[str, Any]) -> Grid:
    w, h = 44, 28
    g = _blank(w, h)
    _carve_rect(g, 1, 1, w - 2, h - 2)
    px, py = 8, 7
    for row in range(2):
        for col in range(4):
            g[py + row * 3][px + col * 3] = "F"
    g[py + 1][px - 3] = "N"
    g[h // 2][w - 8] = "X"
    g[h - 6][w // 2] = "P"
    reserved = {(x, y) for y in range(py - 2, py + 6) for x in range(px - 4, px + 12)}
    reserved |= {(x, y) for y in range(h // 2 - 2, h // 2 + 3) for x in range(w - 11, w - 5)}
    reserved |= {(x, y) for y in range(h - 8, h - 3) for x in range(w // 2 - 2, w // 2 + 3)}
    trees = 0
    while trees < 38:
        x, y = rng.randint(2, w - 3), rng.randint(2, h - 3)
        if (x, y) in reserved or g[y][x] != ".":
            continue
        g[y][x] = "#"
        if len(_bfs(g, (w // 2, h - 6))) < sum(c != "#" for row in g for c in row):
            g[y][x] = "."
            continue
        trees += 1
    return g


def _level_horror(rng: random.Random, p: Dict[str, Any]) -> Grid:
    g, rooms = _rooms_level(rng, 56, 38, 9, (5, 8), 1)
    start = rooms[0]
    _place(g, start, "P", rng)
    d = _bfs(g, _find(g, "P")[0])
    ordered = sorted(rooms[1:], key=lambda r: d.get(_room_center(r), 0))
    key_room, exit_room = ordered[-1], ordered[-2]
    _place(g, key_room, "K", rng)
    _place(g, exit_room, "X", rng)
    rest = ordered[:-2]
    for i, r in enumerate(ordered):
        if i >= 1:
            _place(g, r, "E", rng)
        if i % 2 == 0 and i > 0:
            _place(g, r, "L", rng)
    for i, r in enumerate(rest):
        _place(g, r, "A", rng)
        if i % 2 == 0:
            _place(g, r, "M", rng)
        if i % 3 == 1:
            _place(g, r, "Y", rng)
    return g


LEVEL_BUILDERS = {
    "extraction": _level_extraction,
    "arena": _level_arena,
    "soulslike": _level_soulslike,
    "cozy": _level_cozy,
    "horror": _level_horror,
}

LEGENDS: Dict[str, Dict[str, Dict[str, str]]] = {
    "extraction": {"E": {"role": "enemy", "tier": "trash"}, "L": {"role": "enemy", "tier": "elite"},
                   "C": {"role": "marker", "kind": "core"}, "X": {"role": "marker", "kind": "exit"},
                   "M": {"role": "marker", "kind": "medkit"}, "H": {"role": "hazard", "kind": "heat_vent"}},
    "arena": {"O": {"role": "marker", "kind": "portal"}},
    "soulslike": {"E": {"role": "enemy", "tier": "trash"}, "L": {"role": "enemy", "tier": "elite"},
                  "B": {"role": "enemy", "tier": "boss"}, "S": {"role": "marker", "kind": "shrine"},
                  "X": {"role": "marker", "kind": "exit"}},
    "cozy": {"F": {"role": "marker", "kind": "plot"}, "X": {"role": "marker", "kind": "market"},
             "N": {"role": "marker", "kind": "npc"}},
    "horror": {"E": {"role": "enemy", "tier": "stalker"}, "L": {"role": "enemy", "tier": "crawler"},
               "K": {"role": "marker", "kind": "key"}, "X": {"role": "marker", "kind": "exit"},
               "A": {"role": "marker", "kind": "ammo"}, "M": {"role": "marker", "kind": "medkit"},
               "Y": {"role": "marker", "kind": "battery"}},
}

MARKERS: Dict[str, Dict[str, Any]] = {
    "core": {"color": "#5ef2ff", "shape": "diamond", "radius": 9, "label": "CORE", "bob": True},
    "exit": {"color": "#5dff8a", "shape": "ring", "radius": 16, "label": "EXIT"},
    "medkit": {"color": "#ff5d73", "shape": "square", "radius": 7, "label": "+HP"},
    "portal": {"color": "#c86bff", "shape": "ring", "radius": 14, "label": ""},
    "shrine": {"color": "#ffb84d", "shape": "diamond", "radius": 11, "label": "SHRINE (E)"},
    "echo": {"color": "#9fe8ff", "shape": "ring", "radius": 8, "label": "ECHOES", "bob": True},
    "plot": {"color": "#ffd166", "shape": "plot", "radius": 14, "label": ""},
    "market": {"color": "#f4a261", "shape": "square", "radius": 14, "label": "MARKET (E)"},
    "npc": {"color": "#8ecae6", "shape": "circle", "radius": 10, "label": "NEIGHBOUR (E)"},
    "key": {"color": "#ffe066", "shape": "diamond", "radius": 8, "label": "KEY", "bob": True},
    "ammo": {"color": "#c9c9c9", "shape": "square", "radius": 6, "label": "AMMO"},
    "battery": {"color": "#a0ff7a", "shape": "square", "radius": 6, "label": "BATT"},
}


def validate_level(rows: Sequence[str], loop: str) -> List[str]:
    """Static playability proof for a level: shape, spawn, reachability."""
    problems: List[str] = []
    if not rows or any(len(r) != len(rows[0]) for r in rows):
        return ["level rows must be a non-empty rectangle"]
    g = [list(r) for r in rows]
    h, w = len(g), len(g[0])
    if any(g[0][x] != "#" or g[h - 1][x] != "#" for x in range(w)) or any(
            g[y][0] != "#" or g[y][w - 1] != "#" for y in range(h)):
        problems.append("level border must be solid wall")
    spawns = _find(g, "P")
    if len(spawns) != 1:
        return problems + [f"level needs exactly one P spawn, found {len(spawns)}"]
    legend = LEGENDS[loop]
    allowed = set(legend) | {"#", ".", "P"}
    stray = sorted({c for row in g for c in row} - allowed)
    if stray:
        problems.append(f"unknown level glyphs {stray}")
    reach = _bfs(g, spawns[0])
    unreachable = [(x, y) for y, row in enumerate(g) for x, c in enumerate(row)
                   if c not in "#" and (x, y) not in reach]
    if unreachable:
        problems.append(f"{len(unreachable)} walkable tiles unreachable from spawn")
    required = {
        "extraction": {"C", "X"}, "arena": {"O"}, "soulslike": {"B", "S", "X"},
        "cozy": {"F", "X"}, "horror": {"K", "X"},
    }[loop]
    for ch in sorted(required):
        if not _find(g, ch):
            problems.append(f"level missing required glyph {ch!r} ({legend[ch].get('kind') or legend[ch].get('tier')})")
    return problems


def generate_level(loop: str, seed_int: int, params: Mapping[str, Any]) -> List[str]:
    """Build a validated level for ``loop``; retries a few seeds on failure."""
    last: List[str] = []
    for attempt in range(8):
        rng = random.Random(seed_int * 131 + attempt)
        try:
            g = LEVEL_BUILDERS[loop](rng, dict(params))
        except PlayableExportError as exc:
            last = [str(exc)]
            continue
        rows = ["".join(r) for r in g]
        problems = validate_level(rows, loop)
        if not problems:
            return rows
        last = problems
    raise PlayableExportError(f"could not generate a valid {loop} level: {last}")


# ---------------------------------------------------------------------------
# Config: era pack + intake axes + blueprint components -> game rules
# ---------------------------------------------------------------------------

def _num(container: Any, key: str, default: float) -> float:
    if isinstance(container, Mapping):
        value = container.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value:
            return float(value)
    return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _hex(color: str, fallback: str = "#808080") -> Tuple[int, int, int]:
    text = color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color or "") else fallback
    return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def _mix(color: str, other: str, t: float) -> str:
    a, b = _hex(color), _hex(other)
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _palette(pack: Mapping[str, Any], loop: str) -> Dict[str, str]:
    hw = pack.get("hardware") if isinstance(pack.get("hardware"), Mapping) else {}
    pal = [c for c in (hw.get("palette") or []) if isinstance(c, str)] or ["#4739b8", "#37beee", "#e36953", "#edb74c"]
    base = pal[0]
    accent = pal[min(2, len(pal) - 1)]
    darkness = {"horror": 0.85, "soulslike": 0.78, "extraction": 0.72, "arena": 0.7, "cozy": 0.35}[loop]
    ground = "#3f7d3a" if loop == "cozy" else "#101018"
    floor_a = _mix(_mix(base, ground, 0.6), "#000000", darkness * 0.6)
    return {
        "floor_a": floor_a,
        "floor_b": _mix(floor_a, "#ffffff", 0.05),
        "wall": _mix(base, "#000000", darkness) if loop != "cozy" else "#2d5a27",
        "wall_top": _mix(base, "#ffffff", 0.15),
        "hazard": "#ff7a1a",
        "accent": accent,
        "player": pal[1 % len(pal)] if loop != "horror" else "#e8e8e8",
        "source": list(pal[:8]),
    }


def _viewport(hw: Mapping[str, Any]) -> List[int]:
    vp = hw.get("viewport")
    if (isinstance(vp, (list, tuple)) and len(vp) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in vp)
            and vp[0] >= 320 and vp[1] >= 180):
        return [int(vp[0]), int(vp[1])]
    return [1280, 720]


def _recipe(pack: Mapping[str, Any]) -> Dict[str, Any]:
    for r in pack.get("recipes") or []:
        if isinstance(r, Mapping) and isinstance(r.get("damage"), (int, float)):
            return dict(r)
    return {"id": "sidearm", "family": "kinetic", "damage": 18, "heat": 6.0, "rpm": 300}


def _weapon(loop: str, pack: Mapping[str, Any]) -> Tuple[Dict[str, Any], float]:
    r = _recipe(pack)
    dmg = _clamp(float(r.get("damage", 18)), 6.0, 80.0)
    if loop == "cozy":
        return {"mode": "none", "name": "Watering can", "damage": 0.0, "cooldown": 0.5}, 1.0
    if loop == "soulslike":
        w = {"mode": "melee", "name": "Worn blade", "damage": round(dmg * 2.4, 1), "cooldown": 0.42,
             "reach": 38.0, "arc_degrees": 120.0, "stamina_cost": 18.0, "recipe": r.get("id")}
        return w, w["damage"] / 0.62
    cooldown = round(_clamp(60.0 / max(float(r.get("rpm", 300)), 1.0), 0.1, 0.6), 3)
    w = {"mode": "gun", "name": str(r.get("id", "sidearm")).replace("_", " ").title(), "damage": dmg,
         "cooldown": cooldown, "projectile_speed": 560.0, "spread": 0.05,
         "heat": round(_num(r, "heat", 6.0), 2), "ammo": -1, "recipe": r.get("id")}
    if loop == "horror":
        w.update({"name": "Revolver", "damage": round(dmg * 2.0, 1), "cooldown": 0.55, "ammo": 10, "spread": 0.02})
    return w, w["damage"] / w["cooldown"]


def _tier(name: str, dps: float, ttk: float, lo: float, hi: float, *, speed: float, damage: float,
          radius: float, color: str, label: str, reward: int, **extra: Any) -> Dict[str, Any]:
    spec = {
        "name": name, "hp": round(dps * _clamp(ttk, lo, hi), 1), "speed": round(speed, 1),
        "damage": round(damage, 1), "reach": 24.0, "aggro_tiles": 8, "windup": 0.4, "recover": 0.6,
        "radius": radius, "color": color, "label": label, "reward": reward,
    }
    spec.update(extra)
    return spec


def _enemies(loop: str, pack: Mapping[str, Any], dps: float, player_speed: float, max_hp: float,
             risk: float) -> Dict[str, Dict[str, Any]]:
    ttk = pack.get("ttk") if isinstance(pack.get("ttk"), Mapping) else {}
    base = max_hp * (0.07 + 0.07 * _clamp(risk, 0.0, 1.0))
    t_trash, t_elite, t_boss = _num(ttk, "trash", 1.5), _num(ttk, "elite", 6.0), _num(ttk, "boss", 60.0)
    if loop == "cozy":
        return {}
    if loop == "horror":
        return {
            "stalker": _tier("Stalker", dps, t_elite, 2.0, 3.5, speed=player_speed * 0.42, damage=base * 2.2,
                             radius=13.0, color="#7a1f2b", label="S", reward=2, aggro_tiles=5, windup=0.55,
                             recover=0.9, reach=26.0),
            "crawler": _tier("Crawler", dps, t_trash, 0.4, 1.0, speed=player_speed * 0.9, damage=base * 0.8,
                             radius=9.0, color="#5b6b3a", label="c", reward=1, aggro_tiles=4, windup=0.3),
        }
    tiers: Dict[str, Dict[str, Any]] = {
        "trash": _tier("Grunt", dps, t_trash, 0.5, 2.0, speed=player_speed * (0.72 if loop == "arena" else 0.6),
                       damage=base, radius=11.0, color="#e05555", label="g", reward=1,
                       windup=0.55 if loop == "soulslike" else 0.4),
    }
    if loop == "soulslike":
        tiers["elite"] = _tier("Knight", dps, t_elite, 2.5, 5.0, speed=player_speed * 0.5, damage=base * 1.8,
                               radius=14.0, color="#b04ad9", label="K", reward=5, windup=0.7, recover=0.9,
                               reach=30.0)
        tiers["boss"] = _tier("Boss", dps, t_boss, 9.0, 16.0, speed=player_speed * 0.5, damage=base * 2.3,
                              radius=20.0, color="#ff9f1c", label="B", reward=30, windup=0.8, recover=1.0,
                              reach=34.0, boss=True, aggro_tiles=7)
    else:
        tiers["elite"] = _tier("Spitter", dps, t_elite, 2.0, 5.0, speed=player_speed * 0.5, damage=base * 1.2,
                               radius=14.0, color="#b04ad9", label="S", reward=3, ranged=True, reach=230.0,
                               windup=0.6, recover=1.3, projectile_speed=250.0)
    if loop == "arena":
        tiers["boss"] = _tier("Overlord", dps, t_boss, 6.0, 12.0, speed=player_speed * 0.45, damage=base * 1.3,
                              radius=20.0, color="#ff9f1c", label="O", reward=20, ranged=True, reach=300.0,
                              windup=0.7, recover=1.0, projectile_speed=240.0, boss=True, aggro_tiles=30)
    if loop == "arena":
        for spec in tiers.values():
            spec["relentless"] = True
    return tiers


THEME_FLAVOUR: Dict[str, Dict[str, str]] = {
    "extraction": {"win": "You got out with the haul.", "lose": "The facility keeps what it takes."},
    "arena": {"win": "The crowd roars. Arena cleared.", "lose": "Out of credits. Insert coin."},
    "soulslike": {"win": "The seal breaks. Dawn, at last.", "lose": "Hollowed. The cycle continues."},
    "cozy": {"win": "Festival time! The whole village celebrates.", "lose": "The season ends; next year will be kinder."},
    "horror": {"win": "You escaped into the grey morning.", "lose": "The dark closed in."},
}

BOSS_NAMES: Dict[str, str] = {
    "fantasy": "the Hollow King", "dark-fantasy": "the Ashen Warden", "sci-fi": "the Core Sentinel",
    "horror": "the Thing Below", "cyberpunk": "the Chrome Saint", "post-apocalyptic": "the Rust Tyrant",
}


def build_config(pack: Mapping[str, Any], *, loop: str, title: str, era: str, seed: str,
                 answers: Optional[Mapping[str, Any]] = None, components: Sequence[str] = (),
                 axes: Optional[Mapping[str, float]] = None, level_rows: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Derive the full game config (the ``Game.CONFIG`` constant) from the forge output."""
    if loop not in LOOPS:
        raise PlayableExportError(f"unknown loop {loop!r}; expected one of {LOOPS}")
    if not isinstance(pack, Mapping):
        raise PlayableExportError("pack is required")
    answers = dict(answers or {})
    axes = dict(axes or {})
    risk = _num(axes, "risk", 0.5)
    tempo = _num(axes, "tempo", 0.5)
    player_pack = pack.get("player") if isinstance(pack.get("player"), Mapping) else {}
    heat_pack = pack.get("heat") if isinstance(pack.get("heat"), Mapping) else {}
    session = pack.get("session") if isinstance(pack.get("session"), Mapping) else {}
    speed = _clamp(_num(player_pack, "speed", 160.0), 120.0, 220.0)
    max_hp = _clamp(_num(player_pack, "max_health", 100.0), 60.0, 200.0)
    weapon, dps = _weapon(loop, pack)
    seed_int = int(seed[:8], 16) & 0x7FFFFFFF
    kinds = set(components)
    params = {"cores_total": 4}
    rows = list(level_rows) if level_rows is not None else generate_level(loop, seed_int, params)
    palette = _palette(pack, loop)
    theme = str(answers.get("theme") or "").lower()
    flavour = THEME_FLAVOUR[loop]
    rules: Dict[str, Any] = {"win_text": flavour["win"], "lose_text": flavour["lose"], "hazard_dps": 4.0}
    if loop == "extraction":
        rules.update({
            "collapse_seconds": round(_clamp(_num(session, "collapse_max", 300.0) * 0.6, 180.0, 360.0), 1),
            "cores_required": 3, "reinforce_seconds": round(_clamp(12.0 - 6.0 * tempo, 5.0, 12.0), 2),
            "max_alive": 14, "medkit_heal": 35.0,
        })
    elif loop == "arena":
        extra = 1 if tempo > 0.75 else 0
        rules.update({
            "waves": [["trash"] * (5 + extra), ["trash"] * (7 + extra) + ["elite"],
                      ["trash"] * (8 + extra) + ["elite"] * 2, ["trash"] * (9 + extra) + ["elite"] * 3,
                      ["trash"] * 6 + ["elite"] * 2 + ["boss"]],
            "credits": 3 if era == "arcade_golden_age" else 2, "spawn_interval": round(_clamp(0.9 - 0.4 * tempo, 0.4, 0.9), 2),
            "intermission": 3.0, "combo_window": 2.5, "medkit_drop": 0.15, "medkit_heal": 30.0,
        })
    elif loop == "soulslike":
        rules.update({"max_deaths": 10, "boss_name": BOSS_NAMES.get(theme, "the Warden")})
    elif loop == "cozy":
        rules.update({"goal_coins": 120, "start_seeds": 4, "start_coins": 0, "days": 4, "day_seconds": 90.0,
                      "grow_seconds": 10.0, "seed_price": 3, "crop_price": 12, "bumper_chance": 0.2})
    elif loop == "horror":
        rules.update({"battery_seconds": 150.0, "battery_pickup": 0.4, "ammo_pickup": 6, "medkit_heal": 40.0,
                      "noise_tiles": 9, "light_min": 70.0, "light_max": 230.0})
    companion_on = loop == "cozy" or "jeeves" in kinds or str(answers.get("ai") or "") in {"tactical", "kind", "hype"}
    companion = {
        "enabled": companion_on,
        "name": "Neighbour Wren" if loop == "cozy" else "Jeeves",
        "cooldown": 8.0,
        "intro": {"extraction": "Jeeves: Cores first, sir. Mind the heat.",
                  "arena": "Jeeves: Keep moving and keep firing.",
                  "soulslike": "Jeeves: Rest at the shrine. Watch for the red ring — then roll.",
                  "cozy": "Wren: Welcome! Plant with E, sell at the market stall.",
                  "horror": "Jeeves: Conserve the light. Gunfire carries."}[loop] if companion_on else "",
        "lines": {"low_hp": "You're badly hurt — disengage.", "overheat": "Weapon's cooking. Let it breathe.",
                  "no_ammo": "Empty. Find ammunition or run.", "hazard": "Vent floor — you're overheating.",
                  "collapse": "Structure failing. Exfil now.", "exfil": "That's the quota. Get to exfil.",
                  "key": "The key. Now find the door.", "battery": "Torch is nearly dead."},
        "chatter": ["Crops like company — check them often.", "Bumper harvests happen when you least expect.",
                    "The festival needs coins, not perfection.", "Evenings get dim. Plan your last run to market."],
    }
    hw = pack.get("hardware") if isinstance(pack.get("hardware"), Mapping) else {}
    return {
        "schema": SCHEMA,
        "title": title,
        "era": era,
        "loop": loop,
        "loop_label": LOOP_LABELS[loop],
        "seed": seed,
        "seed_int": seed_int,
        "generation": str(hw.get("key") or "modern"),
        "viewport": _viewport(hw),
        "pixel_snap": bool(hw.get("pixel_snap")) if isinstance(hw.get("pixel_snap"), bool) else False,
        "player": {
            "max_hp": max_hp, "speed": speed,
            "iframe_seconds": round(_clamp(_num(player_pack, "i_frame_ms", 200.0) / 1000.0, 0.12, 0.5), 3),
            "max_stamina": 100.0, "stamina_regen": 38.0 if loop == "soulslike" else 32.0,
            "dodge_cost": 22.0 if loop == "soulslike" else 25.0, "color": palette["player"],
        },
        "weapon": weapon,
        "player_dps": round(dps, 2),
        "heat": {
            "enabled": loop == "extraction" or ("heat" in kinds and weapon["mode"] == "gun"),
            "max": _clamp(_num(heat_pack, "max_heat", 100.0), 40.0, 300.0),
            "cool": round(max(_num(heat_pack, "passive_cool", 6.0), 12.0), 2),
            "per_dodge": round(_num(heat_pack, "sprint_heat_per_sec", 10.0) * 0.5, 2),
            "hazard_per_sec": 20.0, "jam_seconds": 1.5,
        },
        "enemies": _enemies(loop, pack, dps, speed, max_hp, risk),
        "rules": rules,
        "companion": companion,
        "palette": palette,
        "markers": {k: v for k, v in MARKERS.items() if k in {e.get("kind") for e in LEGENDS[loop].values()} | {"medkit", "echo"}},
        "legend": LEGENDS[loop],
        "level": {"tile": 32, "width": len(rows[0]), "height": len(rows), "rows": rows},
        "blueprint_components": sorted(kinds),
        "axes": {k: round(float(v), 4) for k, v in axes.items() if isinstance(v, (int, float))},
    }


# ---------------------------------------------------------------------------
# Placeholder assets (clearly labelled) + project emission
# ---------------------------------------------------------------------------

def _svg(label: str, color: str, shape: str = "circle") -> str:
    body = {
        "circle": f'<circle cx="32" cy="28" r="18" fill="{color}"/>',
        "square": f'<rect x="14" y="10" width="36" height="36" fill="{color}"/>',
        "diamond": f'<polygon points="32,8 52,28 32,48 12,28" fill="{color}"/>',
        "ring": f'<circle cx="32" cy="28" r="18" fill="none" stroke="{color}" stroke-width="6"/>',
        "plot": f'<rect x="10" y="8" width="44" height="40" fill="#5a3b22"/><circle cx="32" cy="28" r="10" fill="{color}"/>',
        "tile": f'<rect x="0" y="0" width="64" height="56" fill="{color}"/>',
    }.get(shape, f'<circle cx="32" cy="28" r="18" fill="{color}"/>')
    safe = re.sub(r"[^A-Za-z0-9 _+()-]", "", label)[:18]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<!-- PLACEHOLDER ASSET generated by Skeleton GameForge: replace before shipping -->'
        '<rect width="64" height="64" fill="#202020"/>' + body +
        '<rect x="0" y="50" width="64" height="14" fill="#ff00ff"/>'
        '<text x="32" y="61" font-size="8" font-family="monospace" text-anchor="middle" fill="#000">PLACEHOLDER</text>'
        f'<title>{safe}</title></svg>\n'
    )


def asset_manifest(config: Mapping[str, Any]) -> Dict[str, Any]:
    pal = config["palette"]
    entries: List[Dict[str, Any]] = [
        {"id": "player", "kind": "sprite", "render": "procedural _draw() in scripts/player.gd",
         "placeholder": "assets/placeholders/player.svg", "color": pal["player"], "shape": "circle"},
        {"id": "floor", "kind": "tileset", "render": "procedural _draw() in scripts/level.gd",
         "placeholder": "assets/placeholders/floor.svg", "color": pal["floor_a"], "shape": "tile"},
        {"id": "wall", "kind": "tileset", "render": "procedural _draw() in scripts/level.gd",
         "placeholder": "assets/placeholders/wall.svg", "color": pal["wall"], "shape": "tile"},
    ]
    for tier, spec in sorted(config["enemies"].items()):
        entries.append({"id": f"enemy_{tier}", "kind": "sprite", "render": "procedural _draw() in scripts/enemy.gd",
                        "placeholder": f"assets/placeholders/enemy_{tier}.svg", "color": spec["color"], "shape": "circle",
                        "label": spec["name"]})
    for kind, spec in sorted(config["markers"].items()):
        entries.append({"id": f"marker_{kind}", "kind": "sprite", "render": "procedural _draw() in scripts/marker.gd",
                        "placeholder": f"assets/placeholders/marker_{kind}.svg", "color": spec["color"],
                        "shape": spec.get("shape", "circle"), "label": spec.get("label") or kind})
    audio = ["sfx_attack", "sfx_hit", "sfx_pickup", "sfx_death", "music_loop"]
    for a in audio:
        entries.append({"id": a, "kind": "audio", "render": "none (silent)", "placeholder": None})
    for e in entries:
        e["status"] = "placeholder"
        e["replace_with"] = f"assets/final/{e['id']}.{'ogg' if e['kind'] == 'audio' else 'png'}"
    return {"schema": "skeleton.forge.assets/v1", "all_placeholder": True,
            "note": "Every visual is procedural placeholder geometry; audio is silent. Replace before shipping.",
            "entries": entries}


def _readme(config: Mapping[str, Any], provenance: Mapping[str, Any]) -> str:
    loop = config["loop"]
    goals = {
        "extraction": "Recover the data cores, then reach EXFIL before the collapse clock hits zero. Firing and "
                      "dodging build weapon HEAT; overheating jams your gun, and heat draws reinforcements.",
        "arena": "Survive every wave pouring out of the portals. Chain kills for a combo multiplier. "
                 "You have continue credits; lose them all and it is game over.",
        "soulslike": "Kindle shrines (E) to heal and set your respawn. Watch the red windup ring and dodge "
                     "through strikes with i-frames. Defeat the boss to break the seal, then reach the EXIT. "
                     "Dying drops your echoes where you fell.",
        "cozy": "Plant seeds on plots (E), harvest when ripe, sell at the MARKET stall (E). "
                "Reach the festival coin goal before the season ends. No combat.",
        "horror": "Your flashlight battery drains and ammo is scarce. Gunfire wakes nearby stalkers. "
                  "Find the KEY, then escape through the EXIT.",
    }[loop]
    return (
        f"# {config['title']}\n\n"
        f"*{config['loop_label']}* generated by **Skeleton GameForge** (era `{config['era']}`, seed `{config['seed']}`).\n\n"
        f"## Goal\n\n{goals}\n\n"
        "## Controls\n\n"
        "| Action | Keys |\n|---|---|\n"
        "| Move | WASD / arrow keys |\n| Attack / fire | Space, J, left mouse (aim with mouse) |\n"
        "| Dodge (i-frames) | Shift, K, right mouse |\n| Interact | E, F |\n"
        "| Pause | Esc, P |\n| Restart | R (after a run ends or while paused) |\n\n"
        "## Run\n\n"
        f"Open the folder in Godot {GODOT_VERSION}+ and press F5, or:\n\n"
        "```\ngodot --path .\n```\n\n"
        "Headless autoplay smoke test (the bot plays the core loop and exits 0 on a win):\n\n"
        "```\ngodot --headless --path . --fixed-fps 60 -- --autoplay --smoke-seconds=300\n```\n\n"
        "## Placeholder assets\n\n"
        "**All art and audio are placeholders.** Visuals are procedural `_draw()` geometry, audio is silent. "
        "`data/asset_manifest.json` lists every asset to replace; labelled stand-ins live in `assets/placeholders/`.\n\n"
        "## Layout\n\n"
        "- `scenes/main.tscn` — main scene (level, actors, loop, HUD)\n"
        "- `scripts/player.gd` — player controller\n- `scripts/enemy.gd` — enemy AI state machine\n"
        f"- `scripts/loops/{loop}.gd` — the core loop rules\n"
        "- `scripts/autoload/game.gd` — forged config (`CONFIG`) and run state\n"
        "- `data/level.txt` — the generated level map\n\n"
        f"Forge provenance: blueprint `{provenance.get('blueprint_id')}`, spec `{provenance.get('spec_id')}`.\n"
    )


def emit_playable(config: Mapping[str, Any], *, provenance: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
    """Return ``{relative_path: text}`` for a complete playable Godot 4 project."""
    loop = config["loop"]
    provenance = dict(provenance or {})
    pack_vp = config.get("viewport") or [1280, 720]
    vw, vh = int(pack_vp[0]), int(pack_vp[1])
    zoom = round(_clamp(vw / 800.0, 0.8, 2.0), 2)
    title = str(config["title"]).replace('"', "'")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "game"
    files: Dict[str, str] = {}
    files["project.godot"] = _fill(_tmpl("project.godot"), {
        "TITLE": title, "DESCRIPTION": f"{config['loop_label']} forged by Skeleton GameForge ({config['era']})",
        "GODOT_VERSION": GODOT_VERSION, "VW": vw, "VH": vh,
        "TEXTURE_FILTER": 0 if config.get("pixel_snap") else 1, "CLEAR_COLOR": "0.04, 0.04, 0.06, 1",
        "LOOP": loop, "ERA": config["era"], "SEED": config["seed"],
    })
    files["export_presets.cfg"] = _fill(_tmpl("export_presets.cfg"), {"SLUG": slug})
    files["scenes/main.tscn"] = _fill(_tmpl("main.tscn"), {"LOOP": loop})
    files["scenes/player.tscn"] = _fill(_tmpl("player.tscn"), {"ZOOM": zoom})
    for name in ("enemy", "marker", "projectile"):
        files[f"scenes/{name}.tscn"] = _tmpl(f"{name}.tscn")
    files["shaders/darkness.gdshader"] = _tmpl("darkness.gdshader")
    config_literal = json.dumps(config, indent="\t", ensure_ascii=False, sort_keys=True)
    files["scripts/autoload/game.gd"] = _fill(_tmpl("game.gd"), {"CONFIG": config_literal})
    files["scripts/autoload/autopilot.gd"] = _tmpl("autopilot.gd")
    for name in ("main", "level", "fx", "player", "enemy", "marker", "projectile", "hud"):
        files[f"scripts/{name}.gd"] = _tmpl(f"{name}.gd")
    files["scripts/loops/loop_base.gd"] = _tmpl("loop_base.gd")
    files[f"scripts/loops/{loop}.gd"] = _tmpl(f"loop_{loop}.gd")
    manifest = asset_manifest(config)
    files["data/asset_manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    for e in manifest["entries"]:
        if e.get("placeholder"):
            files[e["placeholder"]] = _svg(e.get("label") or e["id"], e["color"], e.get("shape", "circle"))
    files["assets/placeholders/README.md"] = (
        "# PLACEHOLDER ASSETS\n\nEverything in this folder is a labelled stand-in generated by Skeleton GameForge.\n"
        "The game renders procedural shapes at runtime; these SVGs document intended sprites.\n"
        "See ../../data/asset_manifest.json for the replacement list.\n")
    files["data/game_config.json"] = json.dumps(config, indent=2, sort_keys=True) + "\n"
    files["data/level.txt"] = "\n".join(config["level"]["rows"]) + "\n"
    files["data/forge_provenance.json"] = json.dumps(provenance, indent=2, sort_keys=True, default=str) + "\n"
    files["README.md"] = _readme(config, provenance)
    return files


# ---------------------------------------------------------------------------
# Static validation
# ---------------------------------------------------------------------------

_RES = re.compile(r'(?:path="|preload\("|load\(")(res://[^"]+)"')
_AUTOLOAD = re.compile(r'^([A-Za-z_]\w*)="\*?res://([^"]+)"', re.M)

REQUIRED_FILES: Tuple[str, ...] = (
    "project.godot", "export_presets.cfg", "scenes/main.tscn", "scenes/player.tscn", "scenes/enemy.tscn",
    "scenes/marker.tscn", "scenes/projectile.tscn", "scripts/main.gd", "scripts/player.gd", "scripts/enemy.gd",
    "scripts/hud.gd", "scripts/level.gd", "scripts/loops/loop_base.gd", "scripts/autoload/game.gd",
    "scripts/autoload/autopilot.gd", "data/asset_manifest.json", "data/game_config.json", "README.md",
)


def validate_project(files: Mapping[str, str]) -> List[str]:
    """Closure + playability checks that need no engine binary."""
    problems: List[str] = []
    for rel in REQUIRED_FILES:
        if rel not in files:
            problems.append(f"missing {rel}")
    if problems:
        return problems
    try:
        config = json.loads(files["data/game_config.json"])
    except ValueError as exc:
        return [f"data/game_config.json is not JSON: {exc}"]
    loop = config.get("loop")
    if loop not in LOOPS:
        return [f"config loop {loop!r} is not a known loop"]
    if f"scripts/loops/{loop}.gd" not in files:
        problems.append(f"loop script scripts/loops/{loop}.gd missing")
    godot = files["project.godot"]
    if "config_version=5" not in godot:
        problems.append("project.godot is not Godot 4")
    main = re.search(r'run/main_scene="res://([^"]+)"', godot)
    if not main or main.group(1) not in files:
        problems.append("main scene missing")
    for name, rel in _AUTOLOAD.findall(godot):
        if rel not in files:
            problems.append(f"autoload {name} -> {rel} missing")
    for rel, body in files.items():
        if not body.strip():
            problems.append(f"empty file {rel}")
        for ref in _RES.findall(body):
            if ref[len("res://"):] not in files:
                problems.append(f"{rel} references missing {ref}")
        if rel.endswith(".gd"):
            head = body.lstrip().split("\n", 1)[0]
            if not head.startswith("extends "):
                problems.append(f"{rel}: first line must be extends")
            for i, line in enumerate(body.split("\n"), 1):
                if line.startswith(" ") and line.strip() and not line.strip().startswith("#"):
                    problems.append(f"{rel}:{i}: space indentation (GDScript here uses tabs)")
                    break
            if "__" in body and re.search(r"__[A-Z][A-Z0-9_]*__", body):
                problems.append(f"{rel}: unfilled template token")
    if "const CONFIG = {" not in files["scripts/autoload/game.gd"]:
        problems.append("game.gd lacks the forged CONFIG constant")
    player = files["scripts/player.gd"]
    for needle in ("move_and_slide", "Input.get_vector", "take_damage", "_iframes"):
        if needle not in player:
            problems.append(f"player controller lacks {needle}")
    loop_src = files.get(f"scripts/loops/{loop}.gd", "")
    if 'Game.finish("win")' not in loop_src:
        problems.append(f"loop {loop} has no win state")
    if 'Game.finish("lose")' not in loop_src + files["scripts/loops/loop_base.gd"]:
        problems.append(f"loop {loop} has no lose state")
    if "func bot_think" not in loop_src:
        problems.append(f"loop {loop} has no autopilot brain")
    problems.extend(validate_level(config.get("level", {}).get("rows") or [], loop))
    for tier in {e["tier"] for e in config["legend"].values() if e.get("role") == "enemy"}:
        if tier not in config.get("enemies", {}):
            problems.append(f"level places enemy tier {tier!r} with no stats")
    if loop == "arena":
        for wave in config["rules"].get("waves") or []:
            for tier in wave:
                if tier not in config["enemies"]:
                    problems.append(f"arena wave spawns unknown tier {tier!r}")
    try:
        manifest = json.loads(files["data/asset_manifest.json"])
    except ValueError:
        manifest = {}
    entries = manifest.get("entries") or []
    if not entries or any(e.get("status") != "placeholder" for e in entries):
        problems.append("asset manifest must list every asset with status=placeholder")
    for e in entries:
        ph = e.get("placeholder")
        if ph and (ph not in files or "PLACEHOLDER" not in files[ph]):
            problems.append(f"placeholder asset {ph} missing or unlabelled")
    if "PLACEHOLDER" not in files["scripts/hud.gd"]:
        problems.append("HUD does not label placeholder art")
    return problems


# ---------------------------------------------------------------------------
# Headless autoplay smoke (reuses the playtest gate's binary + log scan)
# ---------------------------------------------------------------------------

_PRODUCTION_MARKERS = ("K_SERVICE", "KUBERNETES_SERVICE_HOST", "WEBSITE_INSTANCE_ID", "DYNO")


def _production_host() -> bool:
    import os
    env = os.environ
    if str(env.get("EMERGENT_DEPLOY", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if str(env.get("ENVIRONMENT", "")).strip().lower() in {"prod", "production", "staging"}:
        return True
    return any(env.get(m) for m in _PRODUCTION_MARKERS)


def parse_smoke(log: str) -> Optional[Dict[str, Any]]:
    for line in (log or "").splitlines():
        if line.startswith("FORGE_SMOKE "):
            try:
                data = json.loads(line[len("FORGE_SMOKE "):])
            except ValueError:
                return None
            return data if isinstance(data, dict) else None
    return None


def smoke_run(project_dir: str | Path, *, binary: Optional[str] = None, seconds: float = 300.0,
              timeout: float = 240.0, import_first: bool = True) -> Dict[str, Any]:
    """Let the Autopilot play the project headless; ``passed`` means it won cleanly."""
    from skeleton.forge.playtest import _run, resolve_binary, scan_log

    root = Path(project_dir)
    if not (root / "project.godot").is_file():
        raise PlayableExportError(f"no project.godot in {root}")
    path, source, verified = resolve_binary(binary)
    base: Dict[str, Any] = {"binary": path, "binary_source": source, "verified": verified,
                            "smoke_seconds": seconds, "passed": False, "errors": []}
    if path is None:
        return {**base, "status": "unavailable", "reason": source}
    if _production_host():
        return {**base, "status": "unavailable", "reason": "execution disabled on production host"}
    started = time.monotonic()
    steps: List[Dict[str, Any]] = []
    errors: List[str] = []
    if import_first:
        code, log, timed_out = _run([path, "--headless", "--path", str(root), "--import"], root, timeout)
        found = scan_log(log)
        steps.append({"step": "import", "returncode": code, "timed_out": timed_out, "errors": found[:20]})
        errors.extend(found)
        if timed_out:
            errors.append("import timed out")
    report: Optional[Dict[str, Any]] = None
    if not errors:
        cmd = [path, "--headless", "--path", str(root), "--fixed-fps", "60", "--disable-vsync",
               "--", "--autoplay", f"--smoke-seconds={seconds:g}"]
        code, log, timed_out = _run(cmd, root, timeout)
        found = scan_log(log)
        report = parse_smoke(log)
        steps.append({"step": "autoplay", "returncode": code, "timed_out": timed_out,
                      "errors": found[:20], "log_tail": log[-3000:]})
        errors.extend(found)
        if timed_out:
            errors.append(f"autoplay timed out after {timeout:.0f}s")
        if report is None and not timed_out:
            errors.append("autoplay produced no FORGE_SMOKE report")
    outcome = (report or {}).get("outcome")
    passed = not errors and outcome == "win"
    return {**base, "status": "passed" if passed else "failed", "passed": passed, "outcome": outcome,
            "report": report, "errors": errors[:50], "steps": steps,
            "elapsed_s": round(time.monotonic() - started, 3)}


# ---------------------------------------------------------------------------
# End to end: answers -> GameForge -> playable project on disk
# ---------------------------------------------------------------------------

@dataclass
class PlayableExport:
    root: str
    loop: str
    loop_reason: str
    era: str
    title: str
    seed: str
    file_count: int
    problems: List[str]
    forge: Dict[str, Any] = field(default_factory=dict)
    smoke: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return not self.problems and (self.smoke is None or self.smoke.get("status") != "failed")

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": SCHEMA, "root": self.root, "loop": self.loop, "loop_reason": self.loop_reason,
                "era": self.era, "title": self.title, "seed": self.seed, "file_count": self.file_count,
                "problems": list(self.problems), "ok": self.ok, "forge": dict(self.forge), "smoke": self.smoke}


def seed_for(answers: Mapping[str, Any], title: str, loop: str) -> str:
    blob = json.dumps({"answers": {str(k): str(v) for k, v in answers.items()}, "title": title, "loop": loop},
                      sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def forge_playable(answers: Mapping[str, Any], *, title: Optional[str] = None, loop: Optional[str] = None,
                   seed: Optional[str] = None, genesis: Any = None) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any]]:
    """Run questionnaire -> GameForge -> config -> files (in memory).

    Returns ``(config, files, provenance)``.
    """
    if not isinstance(answers, Mapping):
        raise PlayableExportError("answers must be a mapping")
    from skeleton.context import intake as process_intake
    from skeleton.pipelines.gameforge import GameForge

    intake_result = process_intake(answers)
    spec = GameForge(genesis=genesis).run(dict(answers), title=title, target="godot")
    artefact = spec.artefact or {}
    pack = artefact.get("pack")
    if not isinstance(pack, Mapping):
        raise PlayableExportError("GameForge artefact carried no era pack")
    topology = artefact.get("topology") or {}
    components = sorted({str(c.get("kind")) for c in (topology.get("components") or {}).values()
                         if isinstance(c, Mapping) and c.get("kind")})
    era = str(spec.era)
    chosen, reason = (loop, "explicit argument") if loop else choose_loop(era, answers)
    if chosen not in LOOPS:
        raise PlayableExportError(f"unknown loop {chosen!r}; expected one of {LOOPS}")
    game_title = str(spec.title)
    seed = seed or seed_for(answers, game_title, chosen)
    if not re.fullmatch(r"[0-9a-f]{8,64}", seed):
        raise PlayableExportError("seed must be 8-64 lowercase hex chars")
    axes = intake_result.tensor.to_dict().get("axes") or {}
    config = build_config(pack, loop=chosen, title=game_title, era=era, seed=seed, answers=answers,
                          components=components, axes=axes)
    verification = artefact.get("verification") if isinstance(artefact.get("verification"), Mapping) else {}
    provenance = {
        "schema": SCHEMA, "answers": dict(answers), "loop": chosen, "loop_reason": reason, "era": era,
        "title": game_title, "seed": seed, "spec_id": spec.spec_id, "blueprint_id": spec.blueprint_id,
        "blueprint_components": components, "execution_order": artefact.get("execution_order"),
        "forge_file_count": artefact.get("file_count"),
        "forge_verification": {k: verification.get(k) for k in ("accepted", "score") if k in verification},
        "vision": spec.vision,
    }
    files = emit_playable(config, provenance=provenance)
    return config, files, provenance


def export_game(answers: Mapping[str, Any], out_dir: str | Path, *, title: Optional[str] = None,
                loop: Optional[str] = None, seed: Optional[str] = None, overwrite: bool = False,
                smoke: str = "off", binary: Optional[str] = None, smoke_seconds: float = 300.0,
                genesis: Any = None) -> PlayableExport:
    """Questionnaire answers -> playable Godot project at ``out_dir``.

    ``smoke``: ``off`` | ``auto`` (run if a Godot binary is available) |
    ``require`` (unavailable binary counts as failure).
    """
    if smoke not in {"off", "auto", "require"}:
        raise PlayableExportError("smoke must be off, auto or require")
    from skeleton.forge.projector import write_project

    config, files, provenance = forge_playable(answers, title=title, loop=loop, seed=seed, genesis=genesis)
    problems = validate_project(files)
    if problems:
        raise PlayableExportError(f"emitted project failed static validation: {problems[:10]}")
    manifest = write_project(out_dir, files, overwrite=overwrite, meta=provenance)
    result = PlayableExport(root=str(manifest["root"]), loop=config["loop"], loop_reason=provenance["loop_reason"],
                            era=config["era"], title=config["title"], seed=config["seed"],
                            file_count=int(manifest["count"]), problems=[],
                            forge={k: provenance[k] for k in ("spec_id", "blueprint_id", "blueprint_components")})
    if smoke != "off":
        run = smoke_run(out_dir, binary=binary, seconds=smoke_seconds)
        if run["status"] == "unavailable" and smoke == "require":
            run = {**run, "status": "failed", "errors": [f"godot unavailable: {run.get('reason')}"]}
        result.smoke = run
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m skeleton.forge.playable",
                                 description="Forge a playable Godot 4 game from questionnaire answers.")
    ap.add_argument("--answers", help="JSON file or inline JSON object of questionnaire answers")
    ap.add_argument("--genre")
    ap.add_argument("--theme")
    ap.add_argument("--perspective")
    ap.add_argument("--combat")
    ap.add_argument("--progression")
    ap.add_argument("--loop", choices=LOOPS, help="force a core loop archetype")
    ap.add_argument("--title")
    ap.add_argument("--seed")
    ap.add_argument("--out", required=True, help="output project directory")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--smoke", nargs="?", const="auto", default="off", choices=("off", "auto", "require"),
                    help="let the Autopilot play the build headless (needs Godot)")
    ap.add_argument("--smoke-seconds", type=float, default=300.0)
    ap.add_argument("--godot", help="path to a Godot 4 binary")
    args = ap.parse_args(argv)
    answers: Dict[str, Any] = {}
    if args.answers:
        text = args.answers.strip()
        answers = json.loads(text if text.startswith("{") else Path(text).read_text(encoding="utf-8"))
        if not isinstance(answers, dict):
            ap.error("--answers must be a JSON object")
    for key in ("genre", "theme", "perspective", "combat", "progression"):
        if getattr(args, key):
            answers[key] = getattr(args, key)
    if not answers:
        ap.error("provide --answers or at least one of --genre/--theme/--perspective/--combat/--progression")
    result = export_game(answers, args.out, title=args.title, loop=args.loop, seed=args.seed,
                         overwrite=args.overwrite, smoke=args.smoke, binary=args.godot,
                         smoke_seconds=args.smoke_seconds)
    out = result.to_dict()
    if out.get("smoke"):
        out["smoke"] = {k: v for k, v in out["smoke"].items() if k != "steps"}
    print(json.dumps(out, indent=2, default=str))
    return 0 if result.ok else 1


__all__ = [
    "ERA_LOOPS", "LOOPS", "LOOP_LABELS", "PlayableExport", "PlayableExportError", "asset_manifest",
    "build_config", "choose_loop", "emit_playable", "export_game", "forge_playable", "generate_level",
    "parse_smoke", "seed_for", "smoke_run", "validate_level", "validate_project",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
