"""Original chunk-streamed NPC world with one actor identity and bounded LOD.

The 7x7 reference geometry is used as a source-authored kernel and extended
into 3x3 or 5x5 connected chunks. Detailed agents are ONLY simulated when
loaded and scheduled in the active budget; deferred agents retain their exact
last position and do not receive phantom progress, witness events, or teleports.
All world logic is independently replayable from source scenes and actions.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256

from .advanced_unified_npc_world import (
    _sources, _hash, UnifiedWorldError, SIDE as SOURCE_SIDE,
)

SCHEMA = "skeleton.game_builder.original_chunked_npc_world.v1"
CHUNK_EDGE = 7
MAX_STEPS = 128
DIRECTIONS = {"north": (0, -1), "south": (0, 1),
              "east": (1, 0), "west": (-1, 0)}
PHASES = ("bounded_player_action", "direct_source_witness",
          "active_lod_schedule", "complete_source_receipt")
OPTIONS = {
    "chunks_per_side": (3, 5),
    "citizens": tuple(range(8, 129)),
    "active_limit": tuple(range(4, 33)),
    "chunk_radius": (0, 1),
    "max_turns": tuple(range(1, 129)),
    "lod_policy": ("nearest", "fair"),
}
DEFAULTS = {
    "chunks_per_side": 3, "citizens": 16, "active_limit": 12,
    "chunk_radius": 1, "max_turns": 96,
    "lod_policy": "nearest",
}


class ChunkWorldError(UnifiedWorldError):
    """World source, physical action or replay evidence is invalid."""


def _options(options):
    if options is None:
        options = {}
    if type(options) is not dict or set(options) - set(DEFAULTS):
        raise ChunkWorldError("only registered bounded chunk-world controls are supported")
    result = {**DEFAULTS, **options}
    for key, choices in OPTIONS.items():
        if (key == "lod_policy" and
            (type(result[key]) is not str or result[key] not in choices)) or (
            key != "lod_policy" and
            (type(result[key]) is not int or result[key] not in choices)
        ):
            raise ChunkWorldError("invalid original streaming setting: " + key)
    if result["active_limit"] > result["citizens"]:
        raise ChunkWorldError("active detailed budget cannot exceed actual citizen count")
    return result


def _cell(x, y, side):
    return x + y * side


def _xy(cell, side):
    return (cell % side, cell // side)


def _chunk(cell, side):
    x, y = _xy(cell, side)
    return (x // CHUNK_EDGE, y // CHUNK_EDGE)


def _dist(a, b, side):
    x, y = _xy(a, side); u, v = _xy(b, side)
    return abs(x-u) + abs(y-v)


def _neighbors(cell, side):
    x, y = _xy(cell, side)
    for dx, dy in DIRECTIONS.values():
        nx, ny = x+dx, y+dy
        if 0 <= nx < side and 0 <= ny < side:
            yield _cell(nx, ny, side)


def _sight(source, target, blockers, side):
    """Correct world-scale raster line of sight, not the old 7x7 kernel."""
    x0,y0=_xy(source,side);x1,y1=_xy(target,side)
    dx=abs(x1-x0);dy=abs(y1-y0)
    sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1
    error=dx-dy
    while x0!=x1 or y0!=y1:
        twice=2*error
        if twice>-dy:
            error-=dy;x0+=sx
        if twice<dx:
            error+=dx;y0+=sy
        loc=_cell(x0,y0,side)
        if loc in blockers and loc!=target:
            return False
    return True


def _step(source, target, obstacles, occupied, side):
    """Breadth-first shortest-path *single step*, without cell overlap."""
    if source == target:
        return source
    queue = deque([source]); visited = {source: None}
    first = {}
    while queue:
        at = queue.popleft()
        for nxt in _neighbors(at, side):
            if nxt in visited or nxt in obstacles or nxt in occupied:
                continue
            visited[nxt] = at
            first[nxt] = nxt if at == source else first[at]
            if nxt == target:
                return first[nxt]
            queue.append(nxt)
    return source


def _placement(seed, count, side, blocked, reserved):
    """Stable original authored expansion, not externally acquired game IP."""
    locations = [pos for pos in range(side * side)
                 if pos not in blocked and pos not in reserved
                 and pos % CHUNK_EDGE not in (0, CHUNK_EDGE - 1)
                 and (pos // side) % CHUNK_EDGE not in (0, CHUNK_EDGE - 1)]
    locations.sort(key=lambda cell: sha256(
        ("%s:original-citizen:%s" % (seed, cell)).encode()
    ).hexdigest())
    if len(locations) < count:
        raise ChunkWorldError("original source has insufficient uniquely embodied places")
    return locations[:count]


def _init_world(rules, sources, options, seed):
    source = sources["quest_director"]["layout"]
    dialogue = sources["dialogue"]["layout"]
    if source["width"] != SOURCE_SIDE or source["height"] != SOURCE_SIDE:
        raise ChunkWorldError("verified source map must be the original 7x7 kernel")
    chunks = options["chunks_per_side"]
    side = CHUNK_EDGE * chunks
    middle = chunks // 2
    center_offset = middle * CHUNK_EDGE
    def translate(local, cx, cy):
        lx, ly = _xy(local, SOURCE_SIDE)
        return _cell(cx * CHUNK_EDGE + lx, cy * CHUNK_EDGE + ly, side)

    blocked = set()
    for cy in range(chunks):
        for cx in range(chunks):
            for local in source["obstacles"]:
                lx, ly = _xy(local, SOURCE_SIDE)
                # Keep edges connected between chunks even if source internal
                # obstacles happen to touch an authoring kernel boundary.
                if lx not in (0, 6) and ly not in (0, 6):
                    blocked.add(translate(local, cx, cy))
    origin = translate(source["player_spawn"], middle, middle)
    actors = []
    used = set()
    for datum in source["npcs"]:
        idx = datum["id"]
        origin_cell = translate(datum["cell"], middle, middle)
        if origin_cell in blocked or origin_cell in used or origin_cell == origin:
            raise ChunkWorldError("authored NPC source cannot overlap another body or player spawn")
        used.add(origin_cell)
        alias = dialogue["speakers"][idx] if idx < len(dialogue["speakers"]) else None
        actors.append({
            "id": "original_chunk_npc:%03d" % idx, "index": idx,
            "origin_kind": "authored_quest_source_role",
            "source_npc": idx, "dialogue_role": alias["id"] if alias else None,
            "name": alias["name"] if alias else "Original Citizen %03d" % idx,
            "position": origin_cell, "home": origin_cell,
            "work": translate(source["sites"][idx]["cell"], middle, middle),
            "phase": "home", "walked": 0, "deferred_ticks": 0,
            "detailed_ticks": 0, "deferred_streak": 0,
            "longest_deferral": 0, "eligible_deferred_ticks": 0,
            "trust": rules["dialogue"]["starting_trust"],
            "patience": (alias["initial_patience"] if alias else
                         rules["dialogue"]["speaker_patience"]),
            "heard": [], "memories": [], "bond": 0, "supported": 0,
        })
    positions = _placement(seed, options["citizens"]-len(actors),
                           side, blocked, used | {origin})
    sites = []
    for i, original in enumerate(source["sites"]):
        sites.append({
            "id": i, "cell": translate(original["cell"], middle, middle),
            "stock": original["stock"], "aid_received": 0,
            "origin": "reviewed_original_quest_site",
        })
    for local in range(options["citizens"]-len(actors)):
        idx = len(actors)
        pos = positions[local]
        x, y = _xy(pos, side)
        # Safe second job site on an actual navigable road; actor does not
        # automatically teleport there while deferred outside detail budget.
        work = _cell(x, min(side-1, y+2), side)
        if work in blocked:
            work = pos
        actors.append({
            "id": "original_chunk_npc:%03d" % idx, "index": idx,
            "origin_kind": "deterministic_original_generated_role",
            "source_npc": None, "dialogue_role": None,
            "name": "Original Traveller %03d" % idx,
            "position": pos, "home": pos, "work": work,
            "phase": "home", "walked": 0, "deferred_ticks": 0,
            "detailed_ticks": 0, "deferred_streak": 0,
            "longest_deferral": 0, "eligible_deferred_ticks": 0,
            "trust": rules["dialogue"]["starting_trust"],
            "patience": rules["dialogue"]["speaker_patience"],
            "heard": [], "memories": [], "bond": 0, "supported": 0,
        })
    if len(actors) != options["citizens"] or len(used | set(positions)) != len(actors):
        raise ChunkWorldError("unified actor identity or placement collisions")
    return {
        "tick": 0, "side": side, "chunks_per_side": chunks,
        "chunk_size": CHUNK_EDGE, "player": origin,
        "obstacles": sorted(blocked), "actors": actors, "sites": sites,
        "inventory": {
            "supplies": rules["quest_director"]["starting_supplies"],
            "stamina": rules["quest_director"]["stamina"],
            "influence": rules["dialogue"]["starting_influence"],
        },
        "events": [], "quests": [], "dialogues": [], "choices": [],
        "completed": 0, "retired": False, "finished": False,
        "loaded_chunks": [], "detailed_actor_ids": [],
        "scheduler": {
            "detailed_updates": 0, "deferred_actor_turns": 0,
            "physical_moves": 0, "forged_offscreen_events": 0,
            "eligible_deferred_actor_turns": 0,
            "max_deferral_streak": 0,
        },
        "last_events": [], "provenance": "original_chunked_derived_scene",
    }


def _visible(state, opts):
    camera = _chunk(state["player"], state["side"])
    radius = opts["chunk_radius"]
    nearby = [
        actor for actor in state["actors"]
        if max(abs(a-b) for a,b in zip(
            _chunk(actor["position"], state["side"]),camera)) <= radius
    ]
    if opts["lod_policy"] == "fair":
        # Deferral debt wins gradually; inactive citizens remain at exact
        # last physical position and never mint unseen witness statements.
        nearby.sort(key=lambda a: (
            _dist(a["position"], state["player"], state["side"]) -
            4 * a["deferred_streak"], a["index"],
        ))
    else:
        nearby.sort(key=lambda a: (
            _dist(a["position"], state["player"], state["side"]), a["index"],
        ))
    detailed = nearby[:opts["active_limit"]]
    chunks = [
        [x,y] for y in range(opts["chunks_per_side"])
        for x in range(opts["chunks_per_side"])
        if max(abs(x-camera[0]),abs(y-camera[1])) <= radius
    ]
    return detailed, chunks


def _actor(state, idx, eligible):
    if idx < 0 or idx >= len(state["actors"]) or idx not in eligible:
        raise ChunkWorldError("inactive or non-existent original NPC cannot be contacted")
    actor = state["actors"][idx]
    if _dist(actor["position"], state["player"], state["side"]) > 1:
        raise ChunkWorldError("real conversation requires adjacent physical original NPC")
    return actor


def _site(state, idx):
    if not 0 <= idx < len(state["sites"]):
        raise ChunkWorldError("unregistered original authored source site")
    site = state["sites"][idx]
    if _dist(state["player"],site["cell"],state["side"]) > 1:
        raise ChunkWorldError("original site requires physical player proximity")
    return site


def _charge(state, key, value):
    if value < 0 or state["inventory"][key] < value:
        raise ChunkWorldError("finite original streaming "+key+" is insufficient")
    state["inventory"][key] -= value


def _act(state, rules, opts, command, active):
    if state["finished"]:
        raise ChunkWorldError("cannot continue an ended original world")
    side = state["side"];q=rules["quest_director"];d=rules["dialogue"]
    eligible = {actor["index"] for actor in active}
    events = []
    if command.startswith("move:"):
        name = command[5:]
        if name not in DIRECTIONS:
            raise ChunkWorldError("unregistered movement direction")
        x,y = _xy(state["player"],side)
        dx,dy = DIRECTIONS[name]
        nx,ny = x+dx,y+dy
        if not (0<=nx<side and 0<=ny<side):
            raise ChunkWorldError("cannot walk beyond streamed original world")
        target = _cell(nx,ny,side)
        if target in state["obstacles"]:
            raise ChunkWorldError("authored original obstacle blocks physical player")
        if any(a["position"] == target for a in state["actors"]):
            raise ChunkWorldError("player cannot phase through an embodied original NPC")
        _charge(state,"stamina",q["movement_stamina"])
        state["player"] = target
        events.append("original_player_walked_one_global_tile")
    elif command in ("wait","inspect"):
        events.append("original_world_observed_without_phantom_progress")
    elif command == "rest":
        state["inventory"]["stamina"] = min(
            q["stamina"],state["inventory"]["stamina"]+q["rest_stamina"])
        events.append("original_finite_stamina_recovery")
    elif command == "retire":
        if state["completed"] < 1:
            raise ChunkWorldError("optional world ending requires real earned quest")
        state["retired"] = state["finished"] = True
        events.append("voluntary_original_chunked_world_epilogue")
    else:
        verb,separator,index = command.partition(":")
        if not separator or not index.isascii() or not index.isdecimal() or len(index)>3:
            raise ChunkWorldError("unknown or malformed source-bound game action")
        idx = int(index)
        if verb in ("observe","speak","support"):
            actor = _actor(state,idx,eligible)
            if verb == "observe":
                events.append("real_original_citizen_observed_at_single_position")
            elif verb == "speak":
                if actor["patience"] < 1 or len(state["dialogues"]) >= d["lines_per_scene"]:
                    raise ChunkWorldError("original dialogue patience/line budget exhausted")
                quest = next((quest for quest in state["quests"]
                              if quest["status"]=="active" and
                              idx in quest["direct_witnesses"] and
                              idx not in quest["testimonies"]),None)
                actor["patience"] -= 1
                statement = {
                    "actor": actor["id"], "tick": state["tick"],
                    "source": ("firsthand_physical_witness" if quest else
                               "firsthand_unrelated_original_conversation"),
                    "event_id": quest["event_id"] if quest else None,
                }
                state["dialogues"].append(statement)
                actor["memories"].append(statement)
                if quest:
                    quest["testimonies"].append(idx)
                    actor["heard"].append(quest["event_id"])
                events.append("one_real_original_actor_spoke_at_its_actual_tile")
            else:
                quest = next((quest for quest in state["quests"]
                              if quest["status"]=="active" and
                              idx in quest["testimonies"] and
                              quest["choice"] is None),None)
                if quest is None or not d["choice_consequences"]:
                    raise ChunkWorldError("support requires a firsthand source and open original branch")
                if actor["patience"] < 1:
                    raise ChunkWorldError("witness refuses an exhausted social choice")
                _charge(state,"influence",d["support_cost"])
                _charge(state,"supplies",q["help_supplies"])
                actor["patience"] -= 1
                actor["supported"] += 1
                actor["trust"] = min(d["trust_cap"],
                                     actor["trust"]+d["support_trust_gain"])
                actor["bond"] += rules["npc_society"]["help_bond"]
                quest["choice"] = "support"
                state["choices"].append({
                    "actor": actor["id"],"quest_id":quest["id"],
                    "material_cost":q["help_supplies"],
                    "influence_cost":d["support_cost"],"tick":state["tick"],
                })
                events.append("physical_source_witness_received_real_paid_assistance")
        elif verb in ("harvest","repair","claim"):
            site = _site(state,idx)
            if verb == "harvest":
                if site["stock"] < q["gather_units"]:
                    raise ChunkWorldError("source stock is finite and cannot be minted")
                _charge(state,"stamina",q["action_stamina"])
                site["stock"] -= q["gather_units"]
                state["inventory"]["supplies"] += q["gather_units"]
                # Only ACTIVE, physically present, unobstructed actual actors
                # can directly witness this event. Deferred cohorts cannot.
                blockers = set(state["obstacles"])
                witnesses = [
                    a["index"] for a in active
                    if _dist(a["position"],site["cell"],side)<=min(
                        3,q["npc_perception"],q["witness_radius"])
                    and _sight(a["position"],site["cell"],blockers,side)
                ]
                eid = len(state["events"])
                fact = {
                    "id": eid,"kind":"harvest","tick":state["tick"],
                    "site":idx,"position":site["cell"],
                    "direct_witnesses":witnesses,
                }
                if len(state["events"]) >= min(96,q["event_budget"]):
                    raise ChunkWorldError("bounded physical eyewitness event journal full")
                state["events"].append(fact)
                if witnesses and len(state["quests"]) < min(12,q["active_quests"]):
                    state["quests"].append({
                        "id": len(state["quests"]), "event_id":eid,"site":idx,
                        "direct_witnesses":witnesses,"testimonies":[],
                        "choice":None,"followups":0,"status":"active",
                        "ending":None,
                    })
                events.append("source_site_harvested_with_real_active_witnesses")
            elif verb == "repair":
                quest = next((a for a in state["quests"] if
                              a["site"] == idx and a["status"] == "active"
                              and a["choice"] == "support"),None)
                if quest is None or not quest["testimonies"]:
                    raise ChunkWorldError("site repair needs paid firsthand dialogue")
                _charge(state,"supplies",q["help_supplies"])
                _charge(state,"stamina",q["action_stamina"])
                site["aid_received"] += q["help_supplies"]
                quest["followups"] += 1
                events.append("finite_real_material_followup_restored_source_site")
            else:
                quest = next((a for a in state["quests"] if
                              a["site"] == idx and a["status"] == "active"
                              and a["choice"] == "support" and a["testimonies"]),None)
                if quest is None or quest["followups"] < q["consequence_depth"]:
                    raise ChunkWorldError("real source quest not fully materially completed")
                quest["status"] = "resolved";quest["ending"] = "restored"
                state["completed"] += 1
                events.append("original_source_restoration_earned_not_auto_promoted")
        else:
            raise ChunkWorldError("command has no real original world effect")
    state["tick"] += 1
    return events


def _schedule(state,rules,opts):
    active, chunks = _visible(state, opts)
    ids = {a["index"] for a in active}
    occupied = {a["position"] for a in state["actors"]}
    obstacles = set(state["obstacles"])
    period = rules["npc_society"]["day_length"]
    working = state["tick"] % period < period // 2
    moves = []
    for actor in state["actors"]:
        if actor["index"] not in ids:
            actor["deferred_ticks"] += 1
            actor["deferred_streak"] += 1
            actor["longest_deferral"] = max(
                actor["longest_deferral"], actor["deferred_streak"])
            if max(abs(a-b) for a,b in zip(
                _chunk(actor["position"], state["side"]),
                _chunk(state["player"], state["side"]),
            )) <= opts["chunk_radius"]:
                actor["eligible_deferred_ticks"] += 1
                state["scheduler"]["eligible_deferred_actor_turns"] += 1
            state["scheduler"]["max_deferral_streak"] = max(
                state["scheduler"]["max_deferral_streak"],
                actor["deferred_streak"],
            )
        else:
            actor["deferred_streak"] = 0
            current = actor["position"]
            occupied.remove(current)
            goal = actor["work"] if working else actor["home"]
            target = _step(
                current, goal, obstacles, occupied | {state["player"]}, state["side"]
            )
            actor["position"] = target
            actor["phase"] = "work" if working else "home"
            actor["detailed_ticks"] += 1
            state["scheduler"]["detailed_updates"] += 1
            if target != current:
                actor["walked"] += 1
                state["scheduler"]["physical_moves"] += 1
                moves.append({
                    "actor":actor["id"],"from":current,"to":target,
                    "tick":state["tick"],"one_tile":True,
                    "from_chunk":list(_chunk(current,state["side"])),
                    "to_chunk":list(_chunk(target,state["side"])),
                })
            occupied.add(target)
        lifetime=rules["dialogue"]["memory_turns"]
        if lifetime < 1:
            actor["memories"] = []
        else:
            actor["memories"] = [m for m in actor["memories"]
                                if state["tick"]-m["tick"]<lifetime][-32:]
    if (len(occupied) != len(state["actors"]) or
        state["player"] in occupied):
        raise ChunkWorldError("physical actor collision with another citizen or player")
    state["scheduler"]["deferred_actor_turns"] += len(state["actors"])-len(ids)
    state["loaded_chunks"] = chunks
    state["detailed_actor_ids"] = [a["id"] for a in active]
    return moves


def _lod_receipt(world, previous):
    """Per-turn, source-reconstructible proof of exactly which bodies ran."""
    scheduler = world["scheduler"]
    detailed = scheduler["detailed_updates"] - previous["detailed_updates"]
    deferred = scheduler["deferred_actor_turns"] - previous["deferred_actor_turns"]
    eligible_unserved = (scheduler["eligible_deferred_actor_turns"] -
                         previous["eligible_deferred_actor_turns"])
    ids = list(world["detailed_actor_ids"])
    if (len(ids) != detailed or len(set(ids)) != detailed or
        detailed + deferred != len(world["actors"]) or
        not 0 <= eligible_unserved <= deferred):
        raise ChunkWorldError("per-turn original NPC update ledger violates finite detail conservation")
    return {
        "selected_actor_ids": ids,
        "actually_detailed": detailed,
        "deferred": deferred,
        "eligible_but_deferred": eligible_unserved,
        "currently_loaded_chunks": [list(x) for x in world["loaded_chunks"]],
        "longest_global_deferral": scheduler["max_deferral_streak"],
        "phantom_updates": scheduler["forged_offscreen_events"],
    }


def run_chunked_npc_world(actions=(),settings=None,*,scenes=None,seed=0,options=None):
    if type(actions) not in (tuple,list) or len(actions)>MAX_STEPS:
        raise ChunkWorldError("maximum 128 exact bounded original action inputs")
    opts = _options(options)
    rules, sources, origins = _sources(settings,scenes,seed)
    world = _init_world(rules,sources,opts,seed)
    frames = []
    prev = _hash({"schema":SCHEMA,"seed":seed,
                  "source_identities":origins,"opts":opts})
    for i,command in enumerate(actions):
        if type(command) is not str or not 1<=len(command)<=32:
            raise ChunkWorldError("non-string, empty or excessive source command")
        if i>=opts["max_turns"]:
            raise ChunkWorldError("authored original world turn budget exhausted")
        before = _hash(world)
        previous_scheduler = dict(world["scheduler"])
        active,_ = _visible(world,opts)
        observed = _act(world,rules,opts,command,active)
        moves = _schedule(world,rules,opts)
        world["last_events"] = observed + (
            ["bounded_streamed_schedules_advanced"] if moves else [])
        event = {
            "step":i,"command":command,"tick":world["tick"],
            "previous":prev,"before":before,
            "causal_events":observed,"physical_moves":moves,
            "lod_fidelity":_lod_receipt(world, previous_scheduler),
            "after":_hash(world),"ordered_phases":list(PHASES),
        }
        event["digest"] = _hash(event)
        prev = event["digest"]
        frames.append(event)
    report = {
        "schema":SCHEMA,"seed":seed,"settings":rules,"source_scenes":sources,
        "source_identities":origins,"options":opts,
        "commands":list(actions),"state":world,
        "trace":frames,"head_digest":prev,
        "physical_actor_count":len(world["actors"]),
        "streaming_is_deterministic":True,
        "offscreen_movement_was_not_fabricated":True,
        "gameplay_is_native_hardware_certified":False,
        "ai_model_weights_promoted":False,
        "source_files_mutated":False,
        "fully_simulated_offscreen_actor_count":0,
    }
    return {**report,"digest":_hash(report)}


def verify_chunked_npc_world(report):
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise ChunkWorldError("unrecognized original streaming world proof")
    try:
        expected = run_chunked_npc_world(
            report["commands"],report["settings"],
            scenes=report["source_scenes"],seed=report["seed"],
            options=report["options"],
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ChunkWorldError("malformed or unverifiable streamed world receipt") from exc
    if expected != report:
        raise ChunkWorldError("source, actor movement, state or source replay was forged")
    return True


__all__ = [
    "SCHEMA","CHUNK_EDGE","MAX_STEPS","DEFAULTS","PHASES",
    "ChunkWorldError","run_chunked_npc_world","verify_chunked_npc_world",
]
