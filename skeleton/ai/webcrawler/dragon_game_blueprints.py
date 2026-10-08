"""Deterministic genre-aware game design compiler.

Create a *campaign*, not merely a reskinned rectangle. The shared board is
32x20 cells; each genre has different geometry, hazards, goals, opposition and
win conditions. Fixed seed, original content, bounded integer-only generation.
No LLM output is ever spliced into executable source or trusted as a stage.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import deque
from hashlib import sha256
import json

W, H = 32, 20
MAX_STAGE = 8
# Legend: . open, # solid, ^ hazard, * pickup, G exit, E roaming foe,
# ~ water, = platform, + healing, D door, S spawn (player).
TILESET = frozenset(".#^*GE~=+DSKCNB")
GENRES = {
    "arcade_score_attack": "arena",
    "bullet_hell": "arena",
    "run_and_gun": "arena",
    "side_scrolling_platformer": "platform",
    "puzzle_platformer": "platform",
    "metroidvania": "platform",
    "top_down_adventure": "adventure",
    "roguelike": "dungeon",
    "survival_horror": "dungeon",
    "turn_based_rpg": "dungeon",
    "tactical_rpg": "tactics",
    "real_time_strategy": "tactics",
    "racing": "racer",
    "sports": "arena",
    "educational": "adventure",
    "cozy_farming": "adventure",
    "sandbox_builder": "adventure",
}
GAME_MODES = ("arena", "platform", "adventure", "dungeon", "tactics", "racer")
MODE_IDS = {name: i for i, name in enumerate(GAME_MODES)}
PALETTES = {
    "dmg_green": ((8, 24, 32), (48, 96, 76), (139, 172, 103), (220, 240, 174)),
    "cga": ((0, 0, 0), (85, 255, 255), (255, 85, 255), (255, 255, 255)),
    "vga_dusk": ((19, 22, 42), (42, 79, 110), (98, 195, 161), (251, 220, 140)),
    "crt_arcade": ((12, 12, 18), (37, 80, 138), (235, 86, 94), (246, 223, 137)),
    "handheld": ((28, 38, 46), (69, 120, 93), (191, 201, 117), (251, 240, 190)),
    "modern_neon": ((13, 12, 32), (57, 84, 170), (107, 249, 177), (255, 198, 84)),
}

@dataclass(frozen=True)
class Stage:
    stage_id: int
    width: int
    height: int
    terrain: tuple[str, ...]
    start: tuple[int, int]
    goal: tuple[int, int]
    pickups: int
    enemies: int
    difficulty: int
    checksum: str
    quest: dict | None = None

@dataclass(frozen=True)
class Campaign:
    id: str
    style: str
    mode: str
    seed: int
    palette: str
    stages: tuple[Stage, ...]
    mechanics: tuple[str, ...]
    objectives: tuple[str, ...]
    verified_generation: bool
    schema: str = "skeleton.ai.dragon.campaign.v1"

class PRNG:
    """Implementation-independent xorshift32: deterministic across machines."""
    def __init__(self, seed: int):
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 or seed >= (1 << 32):
            raise ValueError("seed must be a uint32")
        self.state = seed or 0x9E3779B9

    def u32(self) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x & 0xFFFFFFFF
        return self.state

    def pick(self, n: int) -> int:
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise ValueError("invalid random bound")
        return self.u32() % n

def _ascii_hash(rows: tuple[str, ...]) -> str:
    return sha256("\n".join(rows).encode("ascii")).hexdigest()

def _fill() -> list[list[str]]:
    board = [["." for _ in range(W)] for _ in range(H)]
    for x in range(W):
        board[0][x] = board[H - 1][x] = "#"
    for y in range(H):
        board[y][0] = board[y][W - 1] = "#"
    return board

def _reachable(board: list[list[str]], start: tuple[int, int], goal: tuple[int, int]) -> bool:
    q = deque([start])
    seen = {start}
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            return True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in seen and 0 <= nx < W and 0 <= ny < H:
                if board[ny][nx] not in "#^~":
                    seen.add((nx, ny))
                    q.append((nx, ny))
    return False

def _carve_dungeon(board: list[list[str]], rng: PRNG, difficulty: int) -> None:
    # Vary room locations; connect them via a Manhattan spanning path.
    rooms = [(2, 3, 8, 6), (13, 2, 19, 6), (23, 4, 29, 9),
             (4, 11, 11, 17), (16, 12, 23, 17)]
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            board[y][x] = "#"
    for left, top, right, bottom in rooms:
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                board[y][x] = "."
    for a, b in zip(rooms, rooms[1:]):
        ax, ay = (a[0] + a[2]) // 2, (a[1] + a[3]) // 2
        bx, by = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
        # Two-cell corridors support actual 2D character movement.
        for x in range(min(ax, bx), max(ax, bx) + 1):
            board[ay][x] = board[min(H - 2, ay + 1)][x] = "."
        for y in range(min(ay, by), max(ay, by) + 1):
            board[y][bx] = board[y][min(W - 2, bx + 1)] = "."
    # Interior cover, never seal a corridor.
    for _ in range(5 + difficulty):
        rx, ry = 2 + rng.pick(W - 4), 2 + rng.pick(H - 4)
        if board[ry][rx] == "." and (rx, ry) not in ((4, 4), (21, 15)):
            if _reachable(board, (4, 4), (21, 15)):
                board[ry][rx] = "#"
                if not _reachable(board, (4, 4), (21, 15)):
                    board[ry][rx] = "."

def _carve_platforms(board: list[list[str]], rng: PRNG, difficulty: int) -> None:
    for x in range(1, W - 1):
        board[H - 2][x] = "="
    for n in range(5 + difficulty):
        x = 3 + ((n * 7 + rng.pick(3)) % (W - 9))
        y = 5 + ((n * 3 + rng.pick(3)) % (H - 9))
        for dx in range(3 + rng.pick(4)):
            if x + dx < W - 1:
                board[y][x + dx] = "="
    for n in range(difficulty + 1):
        board[H - 3][8 + (n * 7) % 19] = "^"

def _carve_race(board: list[list[str]], rng: PRNG, difficulty: int) -> None:
    # Race track is a continuous two-dimensional corridor; hazards line edges.
    for y in range(2, H - 2):
        center = W // 2 + ((y // 3 + difficulty) % 3 - 1) * 3
        for x in range(1, W - 1):
            if abs(x - center) > 5:
                board[y][x] = "#"
        if y % 4 == 0:
            board[y][center + (1 if rng.pick(2) else -1) * 3] = "^"
    for x in range(1, W - 1):
        board[1][x] = board[H - 2][x] = "."

def _decorate(board: list[list[str]], rng: PRNG, *, mode: str, stage_num: int,
              start: tuple[int, int], goal: tuple[int, int]) -> tuple[int, int]:
    pickup_target = 5 + stage_num * 2
    enemy_target = 2 + stage_num
    # Only decorate positions reachable from the spawn. A connected exit is
    # insufficient if the game spawns objectives in inaccessible side pockets.
    reachable = {start}
    frontier = deque([start])
    while frontier:
        cx, cy = frontier.popleft()
        for nx, ny in ((cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)):
            if (nx,ny) not in reachable and 0<=nx<W and 0<=ny<H                     and board[ny][nx] not in "#^~":
                reachable.add((nx,ny))
                frontier.append((nx,ny))
    open_tiles = [(x, y) for y in range(2, H - 2) for x in range(2, W - 2)
                  if (x,y) in reachable and board[y][x] == "." and (x, y) not in (start, goal)
                  and abs(x - start[0]) + abs(y - start[1]) > 2
                  and abs(x - goal[0]) + abs(y - goal[1]) > 2]
    picks, enemies = 0, 0
    for _ in range(pickup_target * 8):
        if not open_tiles or picks >= pickup_target:
            break
        idx = rng.pick(len(open_tiles))
        x, y = open_tiles.pop(idx)
        if board[y][x] == ".":
            board[y][x] = "*"
            picks += 1
    for _ in range(enemy_target * 8):
        if not open_tiles or enemies >= enemy_target:
            break
        idx = rng.pick(len(open_tiles))
        x, y = open_tiles.pop(idx)
        if board[y][x] == ".":
            board[y][x] = "E"
            enemies += 1
    board[start[1]][start[0]] = "S"
    board[goal[1]][goal[0]] = "G"
    return picks, enemies

def design_campaign(*, style: str, seed: int, stages: int = 4,
                    palette: str = "vga_dusk") -> Campaign:
    if style not in GENRES:
        raise ValueError("genre currently has no independently implemented gameplay mode")
    if palette not in PALETTES:
        raise ValueError("unsupported original palette")
    if isinstance(stages, bool) or not isinstance(stages, int) or not 1 <= stages <= MAX_STAGE:
        raise ValueError("campaign stage budget must be 1..8")
    rng = PRNG(seed)
    mode = GENRES[style]
    out: list[Stage] = []
    for n in range(stages):
        board = _fill()
        start, goal = ((4, 4), (21, 15)) if mode == "dungeon" else (
            ((15, H - 3), (15, 1)) if mode == "racer" else
            ((2, H - 4), (W - 3, H - 4)) if mode == "platform" else
            ((3, 3), (W - 4, H - 4)))
        if mode == "dungeon":
            _carve_dungeon(board, rng, n)
        elif mode == "platform":
            _carve_platforms(board, rng, n)
        elif mode == "racer":
            _carve_race(board, rng, n)
        elif mode == "tactics":
            for _ in range(12 + n * 2):
                x, y = 3 + rng.pick(W - 6), 3 + rng.pick(H - 6)
                board[y][x] = "#" if rng.pick(3) == 0 else "="
        else:
            for _ in range(20 + n * 5):
                x, y = 3 + rng.pick(W - 6), 3 + rng.pick(H - 6)
                board[y][x] = "#" if rng.pick(3) == 0 else "^"
        # Prevent maze obstructions from making the goal inaccessible.
        board[start[1]][start[0]] = "."
        board[goal[1]][goal[0]] = "."
        if not _reachable(board, start, goal):
            # Guaranteed radial corridors from spawn to exit.
            sx, sy = start
            gx, gy = goal
            for x in range(min(sx, gx), max(sx, gx) + 1):
                board[sy][x] = "."
            for y in range(min(sy, gy), max(sy, gy) + 1):
                board[y][gx] = "."
        pickups, enemies = _decorate(board, rng, mode=mode, stage_num=n,
                                    start=start, goal=goal)
        from .dragon_campaign_quests import place_quests,quest_record
        quest=place_quests(board,rng=rng,chapter=n,mode=mode,start=start,goal=goal)
        enemies+=quest.guardians
        rows = tuple("".join(row) for row in board)
        if any(len(r) != W or not set(r) <= TILESET for r in rows):
            raise RuntimeError("generator emitted invalid tiles")
        if not _reachable(board, start, goal):
            raise RuntimeError("generator could not prove spawn-to-goal path")
        out.append(Stage(n, W, H, rows, start, goal, pickups, enemies, n + 1,
                         _ascii_hash(rows),quest_record(quest)))
    objectives = {
        "arena": ("Collect crystals", "Dodge patrolling enemies", "Reach the portal"),
        "platform": ("Master jumping", "Avoid dangerous platforms", "Reach the exit"),
        "adventure": ("Explore and collect", "Manage health", "Find the exit"),
        "dungeon": ("Traverse connected rooms", "Avoid enemy patrols", "Escape the dungeon"),
        "tactics": ("Navigate cover", "Manage threats", "Capture the goal"),
        "racer": ("Navigate the winding track", "Avoid track hazards", "Reach the finish"),
    }
    mechanics = {
        "arena": ("movement", "scoring", "collision", "enemy_patrol", "lifebar"),
        "platform": ("movement", "gravity", "jump", "collision", "lifebar"),
        "adventure": ("movement", "collect", "enemy_patrol", "lifebar"),
        "dungeon": ("movement", "connected_rooms", "enemy_patrol", "lifebar"),
        "tactics": ("grid_movement", "cover", "enemy_patrol", "lifebar"),
        "racer": ("steering", "track", "checkpoint", "lifebar"),
    }
    ident = sha256(json.dumps([style, seed, palette, [s.checksum for s in out]],
                              sort_keys=True).encode()).hexdigest()
    return Campaign(ident, style, mode, seed, palette, tuple(out),
                    mechanics[mode], objectives[mode], True)

def campaign_dict(campaign: Campaign) -> dict:
    return asdict(campaign)
