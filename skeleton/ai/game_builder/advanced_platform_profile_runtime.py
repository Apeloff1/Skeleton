"""Deterministic hardware-budget planning runtime for original game targets.

Evaluates and conserves *declared* memory, NPC and estimated frame-work
budgets under an authored era profile. Does not claim to benchmark hardware,
compile native code, emulate a console or prove a game reaches a target FPS.
"""
from __future__ import annotations

ACTIONS=("inspect","spawn:1","spawn:10","despawn:1",
         "stream:4","unstream:4","frame","frame:8","quality:low",
         "quality:medium","quality:high","profile","finish")
_ERAS=("8bit","16bit","32bit","sixth_gen","seventh_gen","modern")
_QUALITY={"low":1,"medium":2,"high":3}


class PlatformProfileActionError(ValueError):
    """Unadmitted era, unsupported allocation or fictitious performance evidence."""


def _int(value,lo,hi,name):
    if type(value) is not int or not lo<=value<=hi:
        raise PlatformProfileActionError("invalid original platform "+name)
    return value


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    return {
        "title":"Original Device Budget "+str(seed%10000),
        "era":config["era"],
        "base_ram_mb":min(4,max(1,config["ram_budget_mb"]//4)),
        "asset_chunk_mb":1,
        "npc_ram_kb":64,
        "work_units_per_npc":2,
        "fixed_frame_work":25,
    }


def normalize_layout(config,layout):
    keys={"title","era","base_ram_mb","asset_chunk_mb",
          "npc_ram_kb","work_units_per_npc","fixed_frame_work"}
    if type(layout) is not dict or set(layout)!=keys:
        raise PlatformProfileActionError("exact original platform scenario required")
    title=layout["title"]
    if type(title) is not str or not 1<=len(title)<=100 or any(ord(c)<32 for c in title):
        raise PlatformProfileActionError("invalid era planning title")
    if layout["era"]!=config["era"] or layout["era"] not in _ERAS:
        raise PlatformProfileActionError("authored hardware era differs from target contract")
    base=_int(layout["base_ram_mb"],0,config["ram_budget_mb"],"base_ram_mb")
    chunk=_int(layout["asset_chunk_mb"],1,256,"asset_chunk_mb")
    npc=_int(layout["npc_ram_kb"],1,65536,"npc memory")
    work=_int(layout["work_units_per_npc"],1,1000,"npc work")
    fixed=_int(layout["fixed_frame_work"],1,100000,"fixed frame work")
    return {"title":title,"era":layout["era"],"base_ram_mb":base,
            "asset_chunk_mb":chunk,"npc_ram_kb":npc,
            "work_units_per_npc":work,"fixed_frame_work":fixed}


def start(config,seed):
    source=normalize_layout(config,default_layout(config,seed))
    return {
        "title":source["title"],"era":source["era"],
        "base_ram_mb":source["base_ram_mb"],
        "asset_chunk_mb":source["asset_chunk_mb"],"npc_ram_kb":source["npc_ram_kb"],
        "work_units_per_npc":source["work_units_per_npc"],
        "fixed_frame_work":source["fixed_frame_work"],
        "npc_count":0,"asset_chunks":0,"quality":"medium",
        "estimated_memory_kb":source["base_ram_mb"]*1024,
        "memory_budget_kb":config["ram_budget_mb"]*1024,
        "fps_target":config["fps_target"],"frames":0,
        "frames_under_budget":0,"frames_over_budget":0,
        "last_work_units":0,"budget_warnings":[],"score":0,
        "turn":0,"finished":False,"failed":False,"events":[],
        "hardware_measured":False,"native_export_compiled":False,
    }


def apply_scene(state,config,layout):
    if state["turn"]:
        raise PlatformProfileActionError("source hardware budget cannot change mid-simulation")
    source=normalize_layout(config,layout)
    for key in ("title","era","base_ram_mb","asset_chunk_mb","npc_ram_kb",
                "work_units_per_npc","fixed_frame_work"):
        state[key]=source[key]
    state["estimated_memory_kb"]=source["base_ram_mb"]*1024


def _ram(state):
    return (state["base_ram_mb"]*1024
            +state["npc_count"]*state["npc_ram_kb"]
            +state["asset_chunks"]*state["asset_chunk_mb"]*1024)


def _frame_budget(config):
    # Work-units are deliberately a declared synthetic budget, *not*
    # milliseconds, render cost or a hardware benchmark.
    return max(10,12000//config["fps_target"])


def step(state,config,action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise PlatformProfileActionError("undeclared or postterminal platform command")
    events=[]
    if action.startswith("spawn:"):
        count=int(action.split(":")[1])
        if state["npc_count"]+count>config["npc_active_budget"]:
            raise PlatformProfileActionError("active NPCs exceed authored device cap")
        prospective=state["estimated_memory_kb"]+count*state["npc_ram_kb"]
        if prospective>state["memory_budget_kb"]:
            raise PlatformProfileActionError("new simulated NPCs violate memory budget")
        state["npc_count"]+=count
        state["estimated_memory_kb"]=prospective
        events.append("conserved_npc_memory_allocated")
    elif action=="despawn:1":
        if state["npc_count"]<=0:
            raise PlatformProfileActionError("cannot free absent player-world NPC")
        state["npc_count"]-=1
        state["estimated_memory_kb"]=_ram(state)
        events.append("actual_active_npc_budget_released")
    elif action=="stream:4":
        prospective=state["estimated_memory_kb"]+4*state["asset_chunk_mb"]*1024
        if prospective>state["memory_budget_kb"]:
            raise PlatformProfileActionError("streaming admission exceeded device RAM envelope")
        state["asset_chunks"]+=4
        state["estimated_memory_kb"]=prospective
        events.append("explicit_game_asset_chunk_memory_admitted")
    elif action=="unstream:4":
        if state["asset_chunks"]<4:
            raise PlatformProfileActionError("cannot unload unowned memory")
        state["asset_chunks"]-=4
        state["estimated_memory_kb"]=_ram(state)
        events.append("actual_declared_asset_memory_released")
    elif action.startswith("quality:"):
        quality=action.split(":")[1]
        if quality==state["quality"]:
            raise PlatformProfileActionError("quality change has no new effect")
        state["quality"]=quality
        events.append("original_era_fidelity_profile_mutated")
    elif action in ("frame","frame:8"):
        count=1 if action=="frame" else 8
        estimated=(state["fixed_frame_work"]
                   +state["npc_count"]*state["work_units_per_npc"]
                   +state["asset_chunks"]*2)*_QUALITY[state["quality"]]
        admitted=_frame_budget(config)
        state["last_work_units"]=estimated
        state["frames"]+=count
        if estimated<=admitted:
            state["frames_under_budget"]+=count
            state["score"]+=count
            events.append("estimated_frame_work_within_declared_budget")
        else:
            state["frames_over_budget"]+=count
            state["budget_warnings"].append({
                "frame":state["frames"],
                "over_by_units":estimated-admitted,
            })
            state["budget_warnings"]=state["budget_warnings"][-16:]
            events.append("estimated_frame_work_over_declared_budget")
    elif action=="profile":
        if not state["frames"]:
            raise PlatformProfileActionError("profiling requires actually executed logical frames")
        state["score"]+=state["frames_under_budget"]//4
        events.append("real_logical_frame_budget_statistics_computed")
    elif action=="finish":
        if not state["frames"] or state["estimated_memory_kb"]>state["memory_budget_kb"]:
            raise PlatformProfileActionError("platform trial requires valid measured logical frames")
        state["finished"]=True
        events.append("estimated_platform_budget_trial_complete_not_hardware_certified")
    else:
        events.append("declared_original_device_budget_inspected")
    state["turn"]+=1
    state["events"]=events
    return events


__all__=["ACTIONS","PlatformProfileActionError","default_layout",
         "normalize_layout","start","apply_scene","step"]
