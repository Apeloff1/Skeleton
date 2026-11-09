"""Sparse, deterministic, disk-backed frontier for original-world pilots.

The world is addressed by signed 32-bit x/y coordinates; terrain is
generated on demand from a stable seed, while persistent edits and travel
history live in SQLite. Storage scales with *visited or modified* tiles,
not the theoretical coordinate grid. This is an abstract top-down survival
world, not a voxel renderer or a generated billion-game claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .original_world_campaign import CampaignError, SCENARIOS

SCHEMA = "original-sparse-frontier.v1"
MIN_COORD = -(2 ** 31)
MAX_COORD = 2 ** 31 - 1
CHUNK = 16
BIOMES = ("meadow", "forest", "wetland", "rock", "steppe", "coast")
DIRECTIONS = {"north": (0, -1), "south": (0, 1),
              "west": (-1, 0), "east": (1, 0)}
ACTIONS = frozenset({
    "move", "forage", "chop", "quarry", "draw_water",
    "plant", "irrigate", "harvest", "build_hut",
    "settle", "repair", "rest", "eat", "scout",
    "restore", "craft", "pledge", "fulfill",
    "weave", "redirect_rain", "end_turn",
})


class FrontierError(CampaignError):
    """Invalid, unavailable or resource-infeasible frontier action."""


@dataclass(frozen=True)
class FrontierTile:
    x: int
    y: int
    biome: str
    food: int
    wood: int
    stone: int
    water: int
    fertility: int
    wildlife: int
    pollution: int = 0
    crop: int = 0
    structure: str = ""
    last_tick: int = 0


@dataclass(frozen=True)
class FrontierPlayer:
    x: int = 0
    y: int = 0
    tick: int = 0
    actions: int = 4
    health: int = 15
    energy: int = 12
    hunger: int = 0
    food: int = 3
    water: int = 4
    wood: int = 3
    stone: int = 2
    seeds: int = 2
    tools: int = 1
    coins: int = 7
    trust: int = 10
    knowledge: int = 0
    promises: int = 0
    honored: int = 0
    quilt: int = 0
    world_phase: int = 0
    rain_west: int = 6
    rain_east: int = 6
    chapter_complete: bool = False
    event_count: int = 0
    event_head: str = "0" * 64


@dataclass(frozen=True)
class FrontierAction:
    verb: str
    option: str = ""
    amount: int = 1


@dataclass(frozen=True)
class FrontierReceipt:
    event_count: int
    event_id: str
    action: FrontierAction
    text: str
    location: tuple[int, int]


def _digest(obj: object) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _roll(seed: str, x: int, y: int, channel: str, mod: int) -> int:
    payload = f"{SCHEMA}:{seed}:{x}:{y}:{channel}".encode("utf-8")
    return int.from_bytes(sha256(payload).digest()[:8], "big") % mod


def _check_coordinate(x: int, y: int) -> None:
    if (type(x) is not int or type(y) is not int
            or not MIN_COORD <= x <= MAX_COORD
            or not MIN_COORD <= y <= MAX_COORD):
        raise FrontierError("frontier coordinate outside declared signed-32-bit grid")


def chunk_of(x: int, y: int) -> tuple[int, int]:
    _check_coordinate(x, y)
    return x // CHUNK, y // CHUNK


def generated_tile(seed: str, x: int, y: int) -> FrontierTile:
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 1024:
        raise FrontierError("invalid frontier seed")
    _check_coordinate(x, y)
    biome = BIOMES[_roll(seed, x, y, "biome", len(BIOMES))]
    food = 2 + _roll(seed, x, y, "food", 7)
    wood = 2 + _roll(seed, x, y, "wood", 7)
    stone = 2 + _roll(seed, x, y, "stone", 7)
    water = 2 + _roll(seed, x, y, "water", 7)
    fert = 2 + _roll(seed, x, y, "fertility", 7)
    wildlife = 2 + _roll(seed, x, y, "wildlife", 7)
    # Coordinates do not imply a finished hand-authored world.
    return FrontierTile(x, y, biome, food, wood, stone,
                        water, fert, wildlife)


def _validate_tile(tile: FrontierTile, x: int, y: int) -> None:
    if not isinstance(tile, FrontierTile) or tile.x != x or tile.y != y:
        raise FrontierError("terrain identity mismatch")
    if tile.biome not in BIOMES or tile.structure not in {
        "", "hut", "village", "garden",
    }:
        raise FrontierError("invalid biome or structure")
    for key in ("food", "wood", "stone", "water",
                "fertility", "wildlife", "pollution", "crop"):
        value = getattr(tile, key)
        if type(value) is not int or not 0 <= value <= 100:
            raise FrontierError("invalid tile resource: " + key)
    if type(tile.last_tick) is not int or not 0 <= tile.last_tick <= 10 ** 9:
        raise FrontierError("invalid tile last_tick")


def _validate_player(player: FrontierPlayer) -> None:
    if not isinstance(player, FrontierPlayer):
        raise FrontierError("invalid player state")
    _check_coordinate(player.x, player.y)
    for field, limit in {
        "tick": 10**9, "actions": 4,
        "health": 20, "energy": 20, "hunger": 20,
        "food": 10000, "water": 10000, "wood": 10000,
        "stone": 10000, "seeds": 10000, "tools": 10000,
        "coins": 10000, "trust": 100, "knowledge": 100,
        "promises": 12, "honored": 10000, "quilt": 10000,
        "world_phase": 11, "rain_west": 12, "rain_east": 12,
        "event_count": 10**9,
    }.items():
        value = getattr(player, field)
        if type(value) is not int or not 0 <= value <= limit:
            raise FrontierError("invalid frontier player " + field)
    if player.rain_west + player.rain_east != 12:
        raise FrontierError("frontier rainfall conservation failure")
    if not isinstance(player.chapter_complete, bool):
        raise FrontierError("invalid chapter state")
    if (not isinstance(player.event_head, str) or len(player.event_head) != 64
            or any(ch not in "0123456789abcdef" for ch in player.event_head)):
        raise FrontierError("frontier head digest invalid")


def _boundary_passable(seed: str, x: int, y: int, phase: int, vertical: bool) -> bool:
    # East/west travel is always possible. At every fifth x-column,
    # north/south remains connected regardless of maze phase. Between
    # these anchors, vertical passages change deterministically by phase.
    if not vertical or x % 5 == 0:
        return True
    return _roll(seed, x, y, "passage:" + str(phase), 4) != 0


class SparseFrontier:
    """Transaction-scoped SQLite world. One state transition per atomic commit."""

    def __init__(self, path: str | Path, world_id: str, seed: str):
        if world_id not in SCENARIOS:
            raise FrontierError("world-law implementation unavailable")
        if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 1024:
            raise FrontierError("invalid seed")
        self.seed = seed
        self.world_id = world_id
        self.db = sqlite3.connect(str(path))
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS frontier_meta(
            key TEXT PRIMARY KEY, value TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS frontier_tile(
            x INTEGER NOT NULL, y INTEGER NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY (x, y)
          );
          CREATE TABLE IF NOT EXISTS frontier_visit(
            x INTEGER NOT NULL, y INTEGER NOT NULL, first_tick INTEGER NOT NULL,
            PRIMARY KEY (x, y)
          );
          CREATE TABLE IF NOT EXISTS frontier_event(
            seq INTEGER PRIMARY KEY,
            digest TEXT NOT NULL,
            payload TEXT NOT NULL
          );
        """)
        saved = self.db.execute(
            "SELECT value FROM frontier_meta WHERE key='identity'"
        ).fetchone()
        identity = {"schema": SCHEMA, "seed": seed, "world_id": world_id}
        if saved is None:
            self.db.execute(
                "INSERT INTO frontier_meta(key,value) VALUES('identity',?)",
                (json.dumps(identity, sort_keys=True),),
            )
            self._put_player(FrontierPlayer())
            self.db.execute(
                "INSERT INTO frontier_visit(x,y,first_tick) VALUES(0,0,0)"
            )
            self.db.commit()
        elif json.loads(saved[0]) != identity:
            self.db.close()
            raise FrontierError("existing frontier database has different world identity")
        _validate_player(self.player())

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "SparseFrontier":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _put_player(self, player: FrontierPlayer) -> None:
        _validate_player(player)
        self.db.execute(
            "INSERT OR REPLACE INTO frontier_meta(key,value) VALUES('player',?)",
            (json.dumps(asdict(player), sort_keys=True),),
        )

    def player(self) -> FrontierPlayer:
        row = self.db.execute("SELECT value FROM frontier_meta WHERE key='player'").fetchone()
        if row is None:
            raise FrontierError("missing player state")
        raw = json.loads(row[0])
        if set(raw) != set(FrontierPlayer.__dataclass_fields__):
            raise FrontierError("unknown player fields")
        state = FrontierPlayer(**raw)
        _validate_player(state)
        return state

    def _get_tile(self, x: int, y: int, now: int) -> FrontierTile:
        _check_coordinate(x, y)
        row = self.db.execute(
            "SELECT payload FROM frontier_tile WHERE x=? AND y=?", (x, y)
        ).fetchone()
        if row is None:
            tile = generated_tile(self.seed, x, y)
        else:
            raw = json.loads(row[0])
            if set(raw) != set(FrontierTile.__dataclass_fields__):
                raise FrontierError("unexpected saved tile fields")
            tile = FrontierTile(**raw)
        _validate_tile(tile, x, y)
        if now < tile.last_tick:
            raise FrontierError("terrain timestamp in the future")
        # Lazy recovery: no iteration over all unvisited cells per turn.
        elapsed = now - tile.last_tick
        recovered = elapsed // 4
        if recovered:
            natural = generated_tile(self.seed, x, y)
            tile = replace(
                tile,
                food=min(natural.food, tile.food + recovered),
                wood=min(natural.wood, tile.wood + recovered // 2),
                water=min(natural.water, tile.water + recovered),
                last_tick=now - (elapsed % 4),
            )
        return tile

    def tile(self, x: int | None = None, y: int | None = None) -> FrontierTile:
        player = self.player()
        at_x = player.x if x is None else x
        at_y = player.y if y is None else y
        return self._get_tile(at_x, at_y, player.tick)

    def _store_tile(self, tile: FrontierTile) -> None:
        _validate_tile(tile, tile.x, tile.y)
        self.db.execute(
            "INSERT OR REPLACE INTO frontier_tile(x,y,payload) VALUES(?,?,?)",
            (tile.x, tile.y, json.dumps(asdict(tile), sort_keys=True)),
        )

    def visited_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM frontier_visit").fetchone()[0]

    def modified_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM frontier_tile").fetchone()[0]

    def passages(self) -> tuple[str, ...]:
        p = self.player()
        choices = []
        for direction, (dx, dy) in DIRECTIONS.items():
            x, y = p.x + dx, p.y + dy
            if not (MIN_COORD <= x <= MAX_COORD and
                    MIN_COORD <= y <= MAX_COORD):
                continue
            if p.world_phase and self.world_id == "topology-02":
                vertical = dy != 0
                edge_y = min(p.y, y)
                if not _boundary_passable(self.seed, x, edge_y,
                                           p.world_phase, vertical):
                    continue
            choices.append(direction)
        return tuple(choices)

    def _execute(self, player: FrontierPlayer, tile: FrontierTile,
                 action: FrontierAction
                 ) -> tuple[FrontierPlayer, FrontierTile | None, str]:
        verb, n, option = action.verb, action.amount, action.option
        if verb not in ACTIONS:
            raise FrontierError("action not implemented")
        if type(n) is not int or not 1 <= n <= 3:
            raise FrontierError("invalid action quantity")
        if not isinstance(option, str) or len(option) > 32:
            raise FrontierError("invalid action option")
        if verb == "end_turn":
            phase = (player.world_phase + 1) % 12
            hunger = min(20, player.hunger + 1)
            health = max(0, player.health - (1 if hunger >= 18 else 0))
            player = replace(
                player, tick=player.tick + 1, actions=4,
                energy=min(20, player.energy + 2),
                hunger=hunger, health=health, world_phase=phase,
            )
            if self.world_id == "ecology-03":
                direction = _roll(self.seed, 0, player.tick, "rain-herd", 2)
                if direction == 0 and player.rain_west > 1:
                    player = replace(player, rain_west=player.rain_west - 1,
                                     rain_east=player.rain_east + 1)
                elif direction == 1 and player.rain_east > 1:
                    player = replace(player, rain_west=player.rain_west + 1,
                                     rain_east=player.rain_east - 1)
            return player, None, "A new world day began"
        if player.actions < 1:
            raise FrontierError("the player must end their turn")
        player = replace(player, actions=player.actions - 1)
        if verb == "move":
            if option not in self.passages():
                raise FrontierError("route is not presently passable")
            dx, dy = DIRECTIONS[option]
            if player.energy < 1:
                raise FrontierError("travel requires energy")
            player = replace(player, x=player.x + dx, y=player.y + dy,
                             energy=player.energy - 1,
                             knowledge=min(100, player.knowledge + 1))
            return player, None, "Traveled to another generated sector"
        if verb in {"forage", "chop", "quarry", "draw_water"}:
            resource, player_field = {
                "forage": ("food", "food"), "chop": ("wood", "wood"),
                "quarry": ("stone", "stone"), "draw_water": ("water", "water"),
            }[verb]
            if getattr(tile, resource) < n:
                raise FrontierError("resource depleted in this sector")
            if getattr(player, player_field) + n > 10000:
                raise FrontierError("player carrying capacity exceeded")
            tile = replace(tile, **{resource: getattr(tile, resource) - n})
            player = replace(player, **{player_field: getattr(player, player_field) + n})
            return player, tile, "Harvested finite local material"
        if verb == "plant":
            if player.seeds < n or player.water < n or tile.crop + n > 12:
                raise FrontierError("infeasible crop planting")
            player = replace(player, seeds=player.seeds - n,
                             water=player.water - n)
            return player, replace(tile, crop=tile.crop + n), "Planted local crops"
        if verb == "irrigate":
            if player.water < n or tile.crop == 0:
                raise FrontierError("irrigation requires crops and water")
            player = replace(player, water=player.water - n)
            return player, replace(tile, fertility=min(100, tile.fertility + n)), "Improved farm soil"
        if verb == "harvest":
            if tile.crop < n or player.food + 2 * n > 10000:
                raise FrontierError("insufficient crop yield")
            player = replace(player, food=player.food + 2 * n)
            return player, replace(tile, crop=tile.crop - n), "Collected planted food"
        if verb == "build_hut":
            if tile.structure or player.wood < 2 or player.stone < 1:
                raise FrontierError("construction needs free land and resources")
            player = replace(player, wood=player.wood - 2,
                             stone=player.stone - 1)
            return player, replace(tile, structure="hut"), "Built a safe local hut"
        if verb == "settle":
            if tile.structure or player.wood < 2 or player.stone < 2:
                raise FrontierError("settlement construction infeasible")
            if self.world_id == "civilization-01" and player.honored < 1:
                raise FrontierError("a civic building requires an honored promise")
            player = replace(player, wood=player.wood - 2,
                             stone=player.stone - 2,
                             trust=min(100, player.trust + 1))
            return player, replace(tile, structure="village"), "Founded an accountable settlement"
        if verb == "repair":
            if not tile.structure or player.wood < 1:
                raise FrontierError("no structure to repair or no timber")
            player = replace(player, wood=player.wood - 1,
                             trust=min(100, player.trust + 1))
            return player, replace(tile, pollution=max(0, tile.pollution - 2)), "Maintained settlement structures"
        if verb == "rest":
            return replace(player, energy=min(20, player.energy + n * 3)), None, "Restored energy"
        if verb == "eat":
            if player.food < n:
                raise FrontierError("insufficient food")
            return replace(player, food=player.food - n,
                           hunger=max(0, player.hunger - 4 * n)), None, "Restored nourishment"
        if verb == "scout":
            if player.energy < n:
                raise FrontierError("scouting requires energy")
            return replace(player, energy=player.energy - n,
                           knowledge=min(100, player.knowledge + 2 * n)), None, "Mapped a local frontier"
        if verb == "restore":
            if player.water < n or player.wood < n:
                raise FrontierError("ecosystem care requires materials")
            player = replace(player, water=player.water - n, wood=player.wood - n,
                             trust=min(100, player.trust + n))
            return player, replace(tile, fertility=min(100, tile.fertility + n),
                                   pollution=max(0, tile.pollution - 2 * n)), "Restored local ecology"
        if verb == "craft":
            if player.wood < n or player.stone < n:
                raise FrontierError("crafting requires wood and stone")
            return replace(player, wood=player.wood - n,
                           stone=player.stone - n,
                           tools=player.tools + n), None, "Crafted durable implements"
        if verb == "pledge":
            if player.promises + n > 12:
                raise FrontierError("civic promise limit reached")
            return replace(player, promises=player.promises + n), None, "Made a binding civic promise"
        if verb == "fulfill":
            if player.promises < n or player.wood < n or player.food < n:
                raise FrontierError("promise lacks obligations or supplies")
            return replace(player, promises=player.promises - n,
                           wood=player.wood - n, food=player.food - n,
                           honored=player.honored + n,
                           trust=min(100, player.trust + 3 * n)), None, "Fulfilled a resource-backed promise"
        if verb == "weave":
            if self.world_id != "serenity-05" or player.wood < n:
                raise FrontierError("living quilt requires its world and materials")
            return replace(player, wood=player.wood - n,
                           quilt=player.quilt + 2 * n,
                           trust=min(100, player.trust + n)), None, "Wove another nonterminal quilt segment"
        if verb == "redirect_rain":
            if self.world_id != "ecology-03" or option not in ("west", "east"):
                raise FrontierError("rain direction not supported in this world")
            if option == "west":
                if player.rain_east < n:
                    raise FrontierError("not enough rain to transfer")
                return replace(player, rain_east=player.rain_east - n,
                               rain_west=player.rain_west + n), None, "Redirected migrating rain"
            if player.rain_west < n:
                raise FrontierError("not enough rain to transfer")
            return replace(player, rain_west=player.rain_west - n,
                           rain_east=player.rain_east + n), None, "Redirected migrating rain"
        raise FrontierError("no executable handler")

    def act(self, action: FrontierAction) -> FrontierReceipt:
        if not isinstance(action, FrontierAction):
            raise FrontierError("invalid action")
        # A transaction synchronizes the player state, modified tile,
        # discovery and evidence receipt. Errors roll back the whole action.
        with self.db:
            player = self.player()
            tile = self._get_tile(player.x, player.y, player.tick)
            next_player, new_tile, text = self._execute(player, tile, action)
            if new_tile is not None:
                self._store_tile(replace(new_tile, last_tick=player.tick))
            before = _digest(asdict(player))
            # Enforce phase and resource conservation at every transition.
            next_player = replace(next_player, event_count=player.event_count + 1)
            event_hash = _digest({
                "schema": SCHEMA, "old": player.event_head,
                "player_before": before, "after": asdict(next_player),
                "action": asdict(action),
                "modified_tile": asdict(new_tile) if new_tile else None,
            })
            next_player = replace(next_player, event_head=event_hash)
            _validate_player(next_player)
            self._put_player(next_player)
            self.db.execute(
                "INSERT OR IGNORE INTO frontier_visit(x,y,first_tick) VALUES(?,?,?)",
                (next_player.x, next_player.y, next_player.tick),
            )
            self.db.execute(
                "INSERT INTO frontier_event(seq,digest,payload) VALUES(?,?,?)",
                (next_player.event_count, event_hash,
                 json.dumps(asdict(action), sort_keys=True)),
            )
            return FrontierReceipt(
                next_player.event_count, event_hash, action,
                text, (next_player.x, next_player.y),
            )

    def nearby_map(self, radius: int = 3) -> str:
        if type(radius) is not int or not 1 <= radius <= 6:
            raise FrontierError("map radius must be 1..6")
        player = self.player()
        cells = []
        for y in range(player.y - radius, player.y + radius + 1):
            line = []
            for x in range(player.x - radius, player.x + radius + 1):
                if not (MIN_COORD <= x <= MAX_COORD and
                        MIN_COORD <= y <= MAX_COORD):
                    line.append("##")
                elif (x, y) == (player.x, player.y):
                    line.append("@@")
                else:
                    biome = self._get_tile(x, y, player.tick).biome
                    icon = {"meadow": "..", "forest": "TT", "wetland": "~~",
                            "rock": "^^", "steppe": "::", "coast": "cc"}[biome]
                    line.append(icon)
            cells.append(" ".join(line))
        return "\n".join(cells) + (
            f"\n({player.x}, {player.y}) | {self.world_id} | "
            f"Turn {player.tick}, AP {player.actions} | "
            f"Visited {self.visited_count()}, edits {self.modified_count()}"
        )
