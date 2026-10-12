"""Original bounded 3D voxel survival-construction reference game.

Source-authored solid cells, deterministic mining/building, granular settling,
day-night illumination, finite inventory and a nonterminal achievement.
This is a small offline gameplay reference, not a renderer or native 3D engine.
"""
from __future__ import annotations

KINDS = ("bedrock", "soil", "stone", "ore", "sand", "wood", "water")
SOLID = frozenset(KINDS[:-1])
MINEABLE = frozenset(("soil", "stone", "ore", "sand", "wood"))
BUILDABLE = ("soil", "stone", "sand", "wood")
DIRECTIONS = {"north": (0, 1), "south": (0, -1),
              "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("inspect", "wait", "rest", "mine", "mine:below", "mine:above",
           "craft:torch", "light", "checkpoint", "retire") + tuple(DIRECTIONS) + tuple(
               "place:" + kind for kind in BUILDABLE)


class VoxelActionError(ValueError):
    """Invalid source-bound voxel command or scene."""


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise VoxelActionError("invalid bounded voxel " + name)
    return value


def _size(config):
    return min(12, config["chunk_edge"])


def _sort(cells):
    return sorted(cells, key=lambda c: (c[2], c[1], c[0]))


def default_layout(config, seed):
    _integer(seed, 0, 2**31 - 1, "seed")
    width = _size(config)
    cells = []
    for y in range(width):
        for x in range(width):
            for z, kind in ((0, "bedrock"), (1, "soil")):
                cells.append([x, y, z, kind, (x * 11 + y * 7 + seed) % config["materials"]])
    for x, y, kind in ((1, 0, "ore"), (2, 1, "ore"),
                       (3, 3, "ore"), (2, 0, "stone"),
                       (5, 4, "wood"), (6, 4, "sand")):
        if x < width and y < width:
            cells.append([x, y, 2, kind, (x * 13 + y * 5 + seed) % config["materials"]])
    return {"title": "Original Voxel Frontier " + str(seed % 1000),
            "size": [width, width, 5], "spawn": [0, 0, 2],
            "cells": _sort(cells), "nonterminal": True}


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
            "title", "size", "spawn", "cells", "nonterminal"}:
        raise VoxelActionError("exact voxel authored scene is required")
    title = layout["title"]
    if type(title) is not str or not 3 <= len(title) <= 64 or not all(
            ch.isalnum() or ch in " _-" for ch in title):
        raise VoxelActionError("unsafe authored voxel title")
    width = _size(config)
    if type(layout["size"]) is not list or layout["size"] != [width, width, 5]:
        raise VoxelActionError("voxel dimensions must match the editor source")
    if type(layout["spawn"]) is not list or layout["spawn"] != [0, 0, 2]:
        raise VoxelActionError("voxel game requires a valid non-obstructed origin")
    if layout["nonterminal"] is not True:
        raise VoxelActionError("original voxel sandbox must permit continuing play")
    raw = layout["cells"]
    if type(raw) is not list or len(raw) > width * width * 5:
        raise VoxelActionError("bounded voxel cell array required")
    checked = []
    seen = set()
    bedrock = set()
    for cell in raw:
        if type(cell) is not list or len(cell) != 5:
            raise VoxelActionError("exact five-column voxel source cells required")
        x = _integer(cell[0], 0, width - 1, "x")
        y = _integer(cell[1], 0, width - 1, "y")
        z = _integer(cell[2], 0, 4, "z")
        kind, variant = cell[3], cell[4]
        if type(kind) is not str or kind not in KINDS:
            raise VoxelActionError("unapproved voxel material")
        _integer(variant, 0, config["materials"] - 1, "material variant")
        pos = (x, y, z)
        if pos in seen or pos == (0, 0, 2):
            raise VoxelActionError("duplicate or player-overlapping source voxel")
        seen.add(pos)
        if z == 0:
            if kind != "bedrock":
                raise VoxelActionError("immutable foundation cannot be replaced")
            bedrock.add((x, y))
        elif kind == "bedrock":
            raise VoxelActionError("bedrock may only occur in immutable foundation")
        checked.append([x, y, z, kind, variant])
    if len(bedrock) != width * width:
        raise VoxelActionError("complete nonmineable bedrock foundation is required")
    if (0, 0, 1) not in seen:
        raise VoxelActionError("authored player spawn lacks a support floor")
    if _sort(checked) != checked:
        raise VoxelActionError("voxel source cells must be canonically ordered")
    return {"title": title, "size": [width, width, 5],
            "spawn": [0, 0, 2], "cells": checked, "nonterminal": True}


def _map(state):
    return {(c[0], c[1], c[2]): (c[3], c[4]) for c in state["cells"]}


def _store(state, blocks):
    state["cells"] = _sort([[*pos, *blocks[pos]] for pos in blocks])


def _light(state, config):
    x, y, z = state["player"]
    daylight = state["turn"] % config["day_length"] < max(1, config["day_length"] // 2)
    illumination = 2 if daylight else 0
    for tx, ty, tz in state["torches"]:
        if abs(tx - x) + abs(ty - y) + abs(tz - z) <= config["light_radius"]:
            illumination = max(illumination, 3)
    state["light"] = illumination
    state["daylight"] = daylight


def start(config, seed):
    layout = normalize_layout(config, default_layout(config, seed))
    state = {
        "title": layout["title"], "size": layout["size"],
        "cells": layout["cells"], "player": list(layout["spawn"]),
        "facing": [1, 0], "turn": 0, "health": config["max_health"],
        "stamina": config["max_stamina"],
        "inventory": {"soil": config["initial_soil"],
                      "stone": config["initial_stone"],
                      "sand": config["initial_sand"],
                      "wood": config["initial_wood"],
                      "ore": 0, "torch": config["initial_torches"]},
        "torches": [], "light": 2, "daylight": True,
        "mined": 0, "ore_mined": 0, "placed": 0, "crafted": 0,
        "fallen_blocks": 0, "visited": [[0, 0]], "checkpoint": False,
        "finished": False, "failed": False, "events": [],
    }
    _light(state, config)
    return state


def apply_scene(state, config, layout):
    if state["turn"] != 0:
        raise VoxelActionError("cannot rewrite a live voxel world")
    source = normalize_layout(config, layout)
    state["title"] = source["title"]
    state["size"] = list(source["size"])
    state["cells"] = [list(cell) for cell in source["cells"]]
    state["player"] = list(source["spawn"])
    _light(state, config)


def _target(state, action):
    x, y, z = state["player"]
    if action == "mine:below":
        return (x, y, z - 1)
    if action == "mine:above":
        return (x, y, z + 1)
    dx, dy = state["facing"]
    return (x + dx, y + dy, z)


def _allowed_sector(config, x, y):
    # Only a small bounded 2x2 active source region is simulated. The much
    # larger configured visibility budget is not misrepresented as loaded.
    sector = (y // 6) * 2 + (x // 6)
    return sector < min(config["visible_chunks"], 4)


def _settle(state, config, blocks):
    if not config["sand_gravity"]:
        return
    moved = 0
    # A single bottom-up pass, one physical voxel per column and tick.
    for x, y, z in sorted(blocks, key=lambda p: (p[2], p[1], p[0])):
        if blocks.get((x, y, z), ("", 0))[0] != "sand" or z < 2:
            continue
        dest = (x, y, z - 1)
        if dest not in blocks and dest != tuple(state["player"]):
            blocks[dest] = blocks.pop((x, y, z))
            moved += 1
    state["fallen_blocks"] += moved


def step(state, config, action):
    if action not in ACTIONS:
        raise VoxelActionError("unrecognized original voxel command")
    if state["finished"] or state["failed"]:
        raise VoxelActionError("a terminated voxel session cannot advance")
    blocks = _map(state)
    events = []
    x, y, z = state["player"]
    if action in DIRECTIONS:
        if state["stamina"] == 0:
            raise VoxelActionError("movement requires physical stamina")
        dx, dy = DIRECTIONS[action]
        nx, ny = x + dx, y + dy
        w, h, _ = state["size"]
        if not (0 <= nx < w and 0 <= ny < h) or not _allowed_sector(config, nx, ny):
            raise VoxelActionError("movement leaves the active authored chunk window")
        nz = z
        if (nx, ny, nz) in blocks and blocks[(nx, ny, nz)][0] in SOLID:
            if nz + 1 >= 5 or (nx, ny, nz + 1) in blocks or (nx, ny, nz) == (0, 0, 0):
                raise VoxelActionError("solid voxel blocks physical traversal")
            nz += 1
            events.append("original_voxel_step_up")
        if (nx, ny, nz) in blocks and blocks[(nx, ny, nz)][0] == "water":
            events.append("original_water_crossing")
        state["player"] = [nx, ny, nz]
        state["facing"] = [dx, dy]
        state["stamina"] -= 1
        sector = [nx // 6, ny // 6]
        if sector not in state["visited"]:
            state["visited"].append(sector)
            state["visited"].sort()
        events.append("physical_three_axis_voxel_traversal")
    elif action.startswith("mine"):
        if not config["destruction"]:
            raise VoxelActionError("mining disabled by reviewed source settings")
        if state["stamina"] < config["mining_energy"]:
            raise VoxelActionError("mining costs finite player energy")
        target = _target(state, action)
        value = blocks.get(target)
        if value is None or value[0] not in MINEABLE:
            raise VoxelActionError("no mineable physical voxel at that location")
        kind = value[0]
        del blocks[target]
        state["inventory"][kind] += 1
        state["mined"] += 1
        if kind == "ore":
            state["ore_mined"] += 1
        state["stamina"] -= config["mining_energy"]
        events.append("finite_original_" + kind + "_mined")
    elif action.startswith("place:"):
        if state["stamina"] < config["building_energy"]:
            raise VoxelActionError("building costs finite player energy")
        kind = action.split(":")[1]
        target = _target(state, action)
        tx, ty, tz = target
        w, h, d = state["size"]
        if not (0 <= tx < w and 0 <= ty < h and 1 <= tz < d) or not _allowed_sector(config, tx, ty):
            raise VoxelActionError("voxel placement exceeds physical world bounds")
        if target in blocks or target == tuple(state["player"]):
            raise VoxelActionError("cannot duplicate or overlap a physical block")
        if (tx, ty, tz - 1) not in blocks:
            raise VoxelActionError("unsupported floating construction rejected")
        if state["inventory"][kind] == 0:
            raise VoxelActionError("no original construction stock remains")
        state["inventory"][kind] -= 1
        blocks[target] = (kind, (tx + ty + state["turn"]) % config["materials"])
        state["placed"] += 1
        state["stamina"] -= config["building_energy"]
        events.append("finite_supported_" + kind + "_construction")
    elif action == "craft:torch":
        if state["inventory"]["wood"] == 0 or state["inventory"]["ore"] == 0:
            raise VoxelActionError("torches require mined ore and harvested timber")
        state["inventory"]["wood"] -= 1
        state["inventory"]["ore"] -= 1
        state["inventory"]["torch"] += 2
        state["crafted"] += 1
        events.append("resource_conserved_torch_crafting")
    elif action == "light":
        if state["inventory"]["torch"] == 0 or list(state["player"]) in state["torches"]:
            raise VoxelActionError("lighting requires a real unused torch and site")
        state["inventory"]["torch"] -= 1
        state["torches"].append(list(state["player"]))
        state["torches"].sort()
        events.append("source_bounded_local_voxel_illumination")
    elif action == "rest":
        state["stamina"] = min(config["max_stamina"], state["stamina"] + 7)
        if state["light"]:
            state["health"] = min(config["max_health"], state["health"] + 1)
        events.append("physical_voxel_recovery")
    elif action == "checkpoint":
        if (state["checkpoint"] or state["ore_mined"] < config["ore_goal"] or
                state["placed"] < 2 or not state["torches"]):
            raise VoxelActionError("conservation and construction evidence not earned")
        state["checkpoint"] = True
        events.append("nonterminal_original_voxel_frontier_checkpoint")
    elif action == "retire":
        if not state["checkpoint"] or state["player"] != [0, 0, 2]:
            raise VoxelActionError("optional retirement requires source-proved progress and home")
        state["finished"] = True
        events.append("optional_completed_voxel_expedition")
    elif action == "inspect":
        events.append("observed_authoritative_original_voxel_state")
    else:
        events.append("bounded_voxel_simulation_wait")
    # Physical settling occurs after each legal command. The initial authored
    # immutable foundation remains unchanged; sand never creates new mass.
    _settle(state, config, blocks)
    # Gravity for the player's feet follows removal of actual supporting cells.
    px, py, pz = state["player"]
    start_z = pz
    while pz > 1 and (px, py, pz - 1) not in blocks:
        pz -= 1
    if pz != start_z:
        state["player"][2] = pz
        state["health"] = max(0, state["health"] -
                              max(0, start_z - pz - 1) * config["fall_damage"])
        events.append("bounded_original_voxel_gravity")
    _store(state, blocks)
    state["turn"] += 1
    _light(state, config)
    if state["light"] == 0:
        state["health"] = max(0, state["health"] - config["darkness_damage"])
        events.append("unlit_night_survival_penalty")
    if state["health"] == 0:
        state["failed"] = True
        events.append("original_voxel_survivor_death")
    return events
