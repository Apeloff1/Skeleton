"""``fill_plan(plan, seed)``: populate a game plan's levels, encounters and loot.

Pipeline, each stage on its own named RNG substream so changing one stage's
parameters never shifts another's output::

    terrain       -> heightmap, erosion, moisture, biomes  (scene per biome)
    dungeon/<m>   -> rooms + corridors (bsp or graph)
    dungeon/keys  -> keyed doors on the critical path
    encounters    -> per-room fights paced along the path
    loot          -> per-room drops from an injected LootSource

The input plan is not mutated. Rooms become levels (exits = neighbouring
rooms), the start room becomes ``start_level`` and the goal room the only
goal level. Anything the plan already has that procgen does not own
(title, player, systems, triggers, assets, existing scenes, extra keys) is
kept. Provenance lands under ``plan["procgen"]`` and per level under
``level["procgen"]``; the validate schema tolerates both.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from .bsp import bsp_layout
from .canonical import canonical_bytes, digest, normalize, q
from .config import ProcgenConfig
from .encounters import EncounterPlan, place_encounters
from .errors import ProcgenError
from .graph_rooms import graph_layout
from .keys import Solution, place_locks, solve_layout
from .layout import Layout, bfs_depths, edge
from .metrics import layout_metrics
from .tiles import assert_tiles_match
from .loot import LootPlan, LootSource, place_loot
from .rng import GENERATOR_VERSION, Streams
from .terrain import Terrain, generate_terrain

SCENE_PREFIX = "pg_"
TILESET_ID = "pg_tiles"


@dataclass(frozen=True)
class ProcgenResult:
    plan: dict
    terrain: Terrain
    layout: Layout
    solution: Solution
    encounters: EncounterPlan
    loot: LootPlan | None
    streams: Streams

    def digest(self) -> str:
        return digest(self.plan)

    def canonical(self) -> bytes:
        return canonical_bytes(self.plan)


def lockable_gating(layout: Layout) -> int:
    """How many critical-path doors could carry a lock that really gates (see ``place_locks``)."""
    path, adj = layout.critical_path, layout.adjacency()
    ok = {d.edge for d in layout.doors if d.lockable}
    return sum(1 for a, b in zip(path, path[1:]) if edge(a, b) in ok
               and layout.goal not in bfs_depths(adj, layout.start, blocked={edge(a, b)}))


def build_layout(streams: Streams, cfg: ProcgenConfig) -> Layout:
    """Roll a layout with enough rooms and lockable gating doors, retrying on a fresh substream per attempt.

    If every attempt falls short, the last layout is used and ``place_locks``
    records the shortfall (or raises with ``strict_locks``).
    """
    last: Layout | None = None
    for attempt in range(cfg.max_attempts):
        rng = streams.stream(f"dungeon/{cfg.dungeon}/{attempt}")
        layout = bsp_layout(rng, cfg.bsp) if cfg.dungeon == "bsp" else graph_layout(rng, cfg.graph)
        last = layout
        if (len(layout.rooms) >= cfg.min_rooms and len(layout.critical_path) > min(cfg.locks, 1)
                and lockable_gating(layout) >= cfg.locks):
            return layout
    assert last is not None
    if len(last.rooms) < 2:
        raise ProcgenError("could not build a layout with at least two rooms")
    return last


def _player(plan: Mapping[str, Any]) -> dict:
    p = plan.get("player")
    if not isinstance(p, Mapping):
        raise ProcgenError("plan needs a player with hp and dps to pace encounters")
    try:
        hp, dps = float(p["hp"]), float(p["dps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProcgenError("player needs numeric hp and dps") from exc
    if hp <= 0 or dps <= 0:
        raise ProcgenError("player hp and dps must be positive")
    return {"hp": hp, "dps": dps}


def _room_biome(terrain: Terrain, layout: Layout, rid: str) -> str:
    r = layout.room(rid).rect
    bx = terrain.biomes.width / layout.width
    by = terrain.biomes.height / layout.height
    return terrain.biomes.dominant(int(r.x * bx), int(r.y * by), int(r.x2 * bx) + 1, int(r.y2 * by) + 1)


def generate(plan: Mapping[str, Any], seed: int | str, *, config: ProcgenConfig | None = None,
             loot_source: LootSource | None = None) -> ProcgenResult:
    if not isinstance(plan, Mapping):
        raise ProcgenError("plan must be a mapping")
    cfg = config or ProcgenConfig.from_mapping(plan.get("procgen_config"))  # type: ignore[arg-type]
    player = _player(plan)
    streams = Streams(seed)
    terrain = generate_terrain(streams, cfg.terrain)
    layout = build_layout(streams, cfg)
    layout = place_locks(layout, streams.stream("dungeon/keys"), cfg.locks,
                         max_key_distance=cfg.limits.max_key_distance, strict=cfg.strict_locks)
    solution = solve_layout(layout)
    if not solution.solvable:  # construction guarantees this; keep the check honest
        raise ProcgenError(f"generated layout not solvable: {solution.as_dict()}")
    tile_check = assert_tiles_match(layout)  # tiles must not offer a route the door graph lacks
    enc = place_encounters(layout, player, streams.stream("encounters"), cfg.encounters)
    loot = None
    if loot_source is not None:
        risk = {rid: rp.damage / player["hp"] for rid, rp in enc.rooms.items()}
        loot = place_loot(risk, loot_source, streams.stream("loot"), cfg.loot, goal=layout.goal)

    out: dict = copy.deepcopy(dict(plan))
    pre = cfg.level_prefix
    lid = {r.id: f"{pre}{r.id}" for r in layout.rooms}
    adj = layout.adjacency()
    locks = layout.locks()
    keys_in: dict[str, list[str]] = {}
    for k, rid in layout.keys.items():
        keys_in.setdefault(rid, []).append(k)

    # scenes / assets
    assets = list(out.get("assets") or [])
    if not any(isinstance(a, Mapping) and a.get("id") == TILESET_ID for a in assets):
        assets.append({"id": TILESET_ID, "kind": "tileset"})
    scenes = [s for s in (out.get("scenes") or []) if not (isinstance(s, Mapping)
                                                            and str(s.get("id", "")).startswith(SCENE_PREFIX))]
    pruned: dict[str, list[str]] = {"scenes": [], "assets": []}
    if cfg.replace_levels and cfg.prune_unused:
        # replaced levels took their scene references with them; drop what nothing uses now
        # (recorded under procgen.pruned so it is visible, not silent)
        pruned["scenes"] = sorted(str(sc.get("id")) for sc in scenes if isinstance(sc, Mapping))
        scenes = []
        pruned["assets"] = sorted(str(a.get("id")) for a in assets
                                  if isinstance(a, Mapping) and a.get("id") != TILESET_ID)
        assets = [a for a in assets if isinstance(a, Mapping) and a.get("id") == TILESET_ID]
    biome_of = {r.id: _room_biome(terrain, layout, r.id) for r in layout.rooms}
    for b in sorted(set(biome_of.values())):
        scenes.append({"id": f"{SCENE_PREFIX}{b}", "assets": [TILESET_ID], "procgen": {"biome": b}})

    # encounters
    system = cfg.system
    systems = list(out.get("systems") or [])
    if system not in systems:
        systems.append(system)
    generated = [e.as_plan(system) for e in enc.all()]
    gen_ids = {e["id"] for e in generated}
    if cfg.replace_levels:
        encounters = generated
    else:
        encounters = [e for e in (out.get("encounters") or [])
                      if not (isinstance(e, Mapping) and e.get("id") in gen_ids)] + generated

    levels = []
    for r in layout.rooms:
        rp = enc.rooms[r.id]
        info: dict[str, Any] = {"room": r.id, "depth": r.depth, "biome": biome_of[r.id], "tags": list(r.tags),
                                "rect": r.rect.as_list(), "keys": sorted(keys_in.get(r.id, [])),
                                "locks": {lid[n]: locks[tuple(sorted((r.id, n)))]  # type: ignore[index]
                                          for n in adj[r.id] if tuple(sorted((r.id, n))) in locks},
                                "difficulty": rp.as_dict(), "intensity": q(rp.damage / player["hp"])}
        if loot is not None:
            info["loot"] = loot.rooms[r.id].as_dict()
        levels.append({"id": lid[r.id], "scene": f"{SCENE_PREFIX}{biome_of[r.id]}",
                       "exits": [lid[n] for n in adj[r.id]], "encounters": [e.id for e in rp.encounters],
                       "procgen": info})
    if not cfg.replace_levels:
        levels = [lv for lv in (out.get("levels") or []) if not (isinstance(lv, Mapping)
                                                                 and str(lv.get("id", "")).startswith(pre))] + levels

    out.update({"assets": assets, "scenes": scenes, "systems": systems, "encounters": encounters,
                "levels": levels, "start_level": lid[layout.start], "goal_levels": [lid[layout.goal]]})
    out["procgen"] = normalize({
        "version": GENERATOR_VERSION,
        "seed": str(seed),
        "config": cfg.as_dict(),
        "streams": streams.as_dict(),
        "terrain": {"receipt": terrain.as_dict()["receipt"], "biome_counts": terrain.biomes.counts(),
                    "walkable_fraction": terrain.walkable_fraction(), "erosion": terrain.erosion.as_dict()},
        "layout": {"method": layout.method, "width": layout.width, "height": layout.height,
                   "tiles": layout.tiles(), "digest": layout.digest(),
                   "critical_path": [lid[x] for x in layout.critical_path],
                   "metrics": {k: v for k, v in layout_metrics(adj, layout.critical_path, layout.start,
                                                                 layout.goal).items() if k != "dead_ends"},
                   "tile_check": tile_check},
        "keys": {k: lid[v] for k, v in sorted(layout.keys.items())},
        "locks": sorted([lid[a], lid[b], k] for (a, b), k in locks.items()),
        "locks_requested": layout.locks_requested,
        "solution": solution.as_dict(),
        "pruned": pruned,
        "difficulty": {"curve": enc.curve(), "cap": cfg.encounters.cap,
                       "intensity": {lid[r]: q(rp.damage / player["hp"]) for r, rp in sorted(enc.rooms.items())}, "hp": player["hp"], "dps": player["dps"]},
        "loot": None if loot is None else {"median_value": loot.median_value, "source": dict(loot.source),
                                           "total": loot.total()},
    })
    return ProcgenResult(out, terrain, layout, solution, enc, loot, streams)


def fill_plan(plan: Mapping[str, Any], seed: int | str, *, config: ProcgenConfig | None = None,
              loot_source: LootSource | None = None) -> dict:
    """Engine entrypoint: a new plan with generated levels, encounters and (if a source is given) loot."""
    return generate(plan, seed, config=config, loot_source=loot_source).plan
