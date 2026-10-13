"""Original witnessed-event quest director and persistent causal world.

Reference world has real tile positions, strict authored event sources, witness
line of sight, memory custody, interpersonal rumors, testimony, branching
quests, finite sites/resources and multiple actually enacted outcomes.
No NPC is omniscient. Never promote rumour to a direct eyewitness.
"""
from __future__ import annotations

from collections import deque

SIDE=7
CELLS=49
EVENTS=("help","harm","discover","repair")
KINDS=("settlement","bridge","grove","archive")
ROLES=("caretaker","scout","merchant","scribe")
ACTIONS=(
    ("north","south","east","west","inspect","wait","wait:4","rest")+
    tuple(f"{action}:{i}" for action in ("help","harm","collect","repair")
          for i in range(4))+
    tuple(f"speak:{i}" for i in range(4))+
    tuple(f"choose:{i}:{branch}" for i in range(12)
          for branch in ("support","exploit"))+
    tuple(f"resolve:{i}" for i in range(12))
)


class QuestDirectorError(ValueError):
    """A world action, witnessed event or authored causal source is invalid."""


def _integer(value,low,high,key):
    if type(value) is not int or not low<=value<=high:
        raise QuestDirectorError("invalid bounded quest "+key)
    return value


def _distance(a,b):
    return abs(a%SIDE-b%SIDE)+abs(a//SIDE-b//SIDE)


def _neighbors(p):
    x,y=p%SIDE,p//SIDE
    return tuple(ny*SIDE+nx for nx,ny in ((x,y-1),(x-1,y),(x+1,y),(x,y+1))
                 if 0<=nx<SIDE and 0<=ny<SIDE)


def _line_open(a,b,obstacles):
    """Bresenham blocks actual sight with signed terrain obstruction."""
    x0,y0=a%SIDE,a//SIDE
    x1,y1=b%SIDE,b//SIDE
    dx=abs(x1-x0);dy=abs(y1-y0)
    sx=1 if x0<x1 else -1
    sy=1 if y0<y1 else -1
    error=dx-dy
    while (x0,y0)!=(x1,y1):
        twice=2*error
        if twice>-dy:
            error-=dy;x0+=sx
        if twice<dx:
            error+=dx;y0+=sy
        if (x0,y0)!=(x1,y1) and (y0*SIDE+x0) in obstacles:
            return False
    return True


def default_layout(config,seed):
    _integer(seed,0,2**31-1,"seed")
    if config["starting_trust"]>config["trust_cap"]:
        raise QuestDirectorError("original source trust cannot exceed NPC trust capacity")
    npc_cells=(9,17,25,33)
    return {
        "width":SIDE,"height":SIDE,"player_spawn":0,
        "obstacles":[11,18,37][:config["obstacle_count"]],
        "sites":[
           {"id":i,"cell":p,"kind":KINDS[i],
            "integrity":config["site_integrity"],"stock":config["site_stock"]}
           for i,p in enumerate((8,16,24,32))
        ],
        "npcs":[
           {"id":i,"cell":npc_cells[i],"role":ROLES[i],
            "trust":config["starting_trust"],"perception":config["npc_perception"]}
           for i in range(config["npc_count"])
        ],
        "climate":("temperate","rainforest","highland","steppe")[seed%4],
        "day_phase":seed%config["day_ticks"],
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "width","height","player_spawn","obstacles","sites","npcs",
        "climate","day_phase"}:
        raise QuestDirectorError("authored living-quest map requires exact original schema")
    _integer(layout["width"],SIDE,SIDE,"map width")
    _integer(layout["height"],SIDE,SIDE,"map height")
    spawn=_integer(layout["player_spawn"],0,CELLS-1,"player spawn")
    blockers=layout["obstacles"]
    if (type(blockers) is not list or len(blockers)>config["obstacle_count"] or
        any(type(p) is not int or not 0<=p<CELLS for p in blockers) or
        len(set(blockers))!=len(blockers)):
        raise QuestDirectorError("original world obstacle placements exceed signed budget")
    seen={spawn}
    for site_group,count,keys in (
       ("sites",4,{"id","cell","kind","integrity","stock"}),
       ("npcs",config["npc_count"],{"id","cell","role","trust","perception"})):
        group=layout[site_group]
        if type(group) is not list or len(group)!=count:
            raise QuestDirectorError("authored world must retain exact source entities")
        for index,entity in enumerate(group):
            if type(entity) is not dict or set(entity)!=keys:
                raise QuestDirectorError("entity source requires exact typed canonical shape")
            if _integer(entity["id"],0,3,"entity id")!=index:
                raise QuestDirectorError("original living entity identities must be canonical")
            cell=_integer(entity["cell"],0,CELLS-1,"entity position")
            if cell in seen or cell in blockers:
                raise QuestDirectorError("real world entities cannot overlap or occupy walls")
            seen.add(cell)
            if site_group=="sites":
                if entity["kind"] not in KINDS:
                    raise QuestDirectorError("unregistered original quest site type")
                _integer(entity["integrity"],1,config["site_integrity"],"site strength")
                _integer(entity["stock"],0,config["site_stock"],"finite site stock")
            else:
                if entity["role"] not in ROLES:
                    raise QuestDirectorError("unregistered NPC profession")
                _integer(entity["trust"],0,config["starting_trust"],"original trust budget")
                _integer(entity["perception"],1,config["npc_perception"],"NPC sight ability")
    climate=layout["climate"]
    if climate not in ("temperate","rainforest","highland","steppe"):
        raise QuestDirectorError("unregistered original cultural climate")
    _integer(layout["day_phase"],0,config["day_ticks"]-1,"day phase")
    reachable={spawn};queue=deque([spawn]);walls=set(blockers)
    while queue:
        for next_cell in _neighbors(queue.popleft()):
            if next_cell not in walls and next_cell not in reachable:
                reachable.add(next_cell);queue.append(next_cell)
    if len(reachable)!=CELLS-len(walls) or not seen.issubset(reachable):
        raise QuestDirectorError("signed world must let player reach every quest site and NPC")
    return {
        **layout,"obstacles":list(blockers),
        "sites":[dict(s) for s in layout["sites"]],
        "npcs":[dict(n) for n in layout["npcs"]],
    }


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    state["world"]=source
    state["player"]=source["player_spawn"]
    state["sites"]=[dict(site) for site in source["sites"]]
    state["npcs"]=[
        {**npc,"memories":[],"heard":[],"suspicion":config["starting_suspicion"],
         "witnessed":0,"rumors_spread":0,"cargo":0,
         "personal_supplies":config["npc_supplies"],
         "energy":config["npc_energy"],"home":npc["cell"],
         "investigations":[],"walks":0}
        for npc in source["npcs"]
    ]
    return state


def start(config,seed):
    _integer(seed,0,2**31-1,"seed")
    state={
        "seed":seed,"world":{},"player":0,"sites":[],"npcs":[],
        "tick":0,"turn":0,"day":0,"gold":config["starting_gold"],
        "supplies":config["starting_supplies"],"stamina":config["stamina"],
        "reputation":config["starting_reputation"],"discovered":[],
        "events_log":[],"quests":[],"quest_archive":[],
        "next_event":0,"next_quest":0,
        "npc_events_generated":0,"next_npc_actor":0,
        "npc_walks":0,"forensic_edges":[],
        "quests_completed":0,"quests_exploited":0,
        "rumor_edges":[],"milestones":[],
        "finished":False,"failed":False,"victory":False,"reason":"",
        "events":[],
    }
    return apply_scene(state,config,default_layout(config,seed))


def _site(state,index):
    return state["sites"][index]


def _adjacent(state,cell):
    return _distance(state["player"],cell)<=1


def _spend(state,key,amount):
    if state[key]<amount:
        raise QuestDirectorError("insufficient physically available "+key)
    state[key]-=amount


def _day_vision(state,config,npc):
    phase=(state["tick"]+state["world"]["day_phase"])%config["day_ticks"]
    night=phase>=config["day_ticks"]*config["night_fraction_percent"]//100
    climate=state["world"]["climate"]
    climate_bonus=(1 if climate=="highland" else
                   -1 if climate=="rainforest" else 0)
    return max(0,min(config["witness_radius"],
                     npc["perception"]+climate_bonus)-
               (config["night_sight_penalty"] if night else 0))


def _remember(npc,event,config,*,direct):
    target="memories" if direct else "heard"
    if not direct and any(m["event_id"]==event["id"]
                          for m in npc["memories"]):
        return False
    if any(m["event_id"]==event["id"] for m in npc[target]):
        return False
    if direct:
        npc["heard"]=[m for m in npc["heard"]
                      if m["event_id"]!=event["id"]]
    while len(npc[target])>=config["memory_records"]:
        npc[target].pop(0)
    npc[target].append({
        "event_id":event["id"],"kind":event["kind"],
        "site_id":event["site_id"],"observed_tick":event["tick"],
        "source":"eyewitness" if direct else "rumor",
    })
    return True


def _emit(state,config,kind,site,events,*,actor="player",physical_source=None):
    if len(state["events_log"])>=config["event_budget"]:
        raise QuestDirectorError("authored finite event memory ledger is full")
    witnesses=[]
    for npc in state["npcs"]:
        if (actor!="npc:"+str(npc["id"]) and
            _distance(npc["cell"],site["cell"])<=_day_vision(state,config,npc)
            and _line_open(npc["cell"],site["cell"],set(state["world"]["obstacles"]))):
            witnesses.append(npc["id"])
    entry={
        "id":state["next_event"],"tick":state["tick"],"kind":kind,
        "site_id":site["id"],"cell":site["cell"],
        "actor":actor,"direct_witnesses":witnesses,
        "rumored_to":[],"original_source":(
            "signed_external_physical_incident" if physical_source is not None else
            "physical_player_world_action" if actor=="player" else
            "physical_npc_world_action"),
    }
    if physical_source is not None:
        entry["physical_source"]=dict(physical_source)
    state["events_log"].append(entry);state["next_event"]+=1
    for n in state["npcs"]:
        if n["id"] in witnesses:
            _remember(n,entry,config,direct=True)
            n["witnessed"]+=1
            delta=(config["empathy_gain"] if kind in ("help","repair") else
                   -config["harm_trust_loss"] if kind=="harm" else 0)
            n["trust"]=max(0,min(config["trust_cap"],n["trust"]+delta))
            if kind=="harm":
                n["suspicion"]=min(config["suspicion_cap"],
                                     n["suspicion"]+config["harm_suspicion"])
    if actor=="player":
        state["reputation"]=max(-config["reputation_cap"],min(config["reputation_cap"],
            state["reputation"]+(config["reputation_gain"] if kind in ("help","repair")
            else -config["reputation_loss"] if kind=="harm" else 0)))
    events.append("original_physical_"+kind+"_event_authored_at_real_site")
    if witnesses:
        events.append("real_local_npcs_directly_witnessed_event")
    else:
        events.append("original_event_had_no_direct_eyewitness")
    # Existing quests can only advance from subsequent real physical acts.
    for quest in state["quests"]:
        if quest["status"]!="active" or quest["site_id"]!=site["id"]:
            continue
        wanted=("harm" if quest["choice"]=="exploit" else
                "repair" if quest["trigger"]=="harm" else "help")
        if kind==wanted and actor=="player":
            quest["material_actions"]+=1
            events.append("existing_original_quest_advanced_by_real_followup")
    if (len(state["quests"])<min(config["active_quests"],12)
        and state["next_quest"]<12
        and kind in EVENTS[:min(4,config["event_rules"])]
        and len(witnesses)>=config["witnesses_required"]):
        # Only a source observed by enough real witnesses becomes a quest.
        # Editor supports many procedural causal rule alternatives, while
        # this 49-cell reference intentionally limits live quest IDs to 12.
        rule_id=(state["seed"]*17+entry["id"]*31+
                 site["id"]*997+EVENTS.index(kind)*131)%config["event_rules"]
        quest={
            "id":state["next_quest"],"origin_event":entry["id"],
            "rule_id":rule_id,"origin_actor":actor,
            "site_id":site["id"],"trigger":kind,"status":"active",
            "witnesses":witnesses[:],"testimonies":[],
            "heard_from":[],"choice":None,"material_actions":0,
            "created_tick":state["tick"],"resolution_tick":None,
            "ending":None,
        }
        state["next_quest"]+=1;state["quests"].append(quest)
        events.append("actual_eyewitnesses_initiated_causal_quest")
    return entry


def _rumors(state,config,events):
    if not config["rumor_enabled"] or state["tick"]%config["rumor_interval"]:
        return
    delivered=0
    # Original source-aware rumors travel along real physical NPC edges,
    # never creating an eyewitness or rewriting the original direct list.
    # Snapshot knowledge first: one rumor can cross only a single physical
    # peer edge per propagation tick, not a magic whole-population chain.
    available={
        n["id"]:list(n["memories"])+list(n["heard"])
        for n in state["npcs"]
    }
    for sender in state["npcs"]:
        for receiver in state["npcs"]:
            if sender is receiver or _distance(sender["cell"],receiver["cell"])>config["rumor_radius"]:
                continue
            if receiver["trust"]<config["rumor_trust_floor"]:
                continue
            for evidence in available[sender["id"]]:
                if delivered>=config["rumor_per_tick"]:return
                source=next((ev for ev in state["events_log"]
                             if ev["id"]==evidence["event_id"]),None)
                if source is None:continue
                if _remember(receiver,source,config,direct=False):
                    source["rumored_to"].append(receiver["id"])
                    edge={"tick":state["tick"],"sender":sender["id"],
                          "recipient":receiver["id"],"event_id":source["id"],
                          "authority":"rumor_only_not_eye_witness"}
                    state["rumor_edges"].append(edge)
                    sender["rumors_spread"]+=1
                    delivered+=1
                    events.append("real_original_npc_to_npc_rumor_transfer")


def _autonomous_npc_action(state,config,events):
    """Actually enact bounded finite NPC behavior from role and nearby sites.

    Never grants the player quest progress or free reputation; NPC-caused
    events may start authentic witnessed quests *only when another NPC saw*.
    """
    if not config["npc_autonomy"] or not state["npcs"] or (
        state["npc_events_generated"]>=config["npc_action_budget"]):
        return
    chosen=state["next_npc_actor"]%len(state["npcs"])
    state["next_npc_actor"]+=1
    npc=state["npcs"][chosen]
    if npc["energy"]<config["npc_action_energy_cost"]:
        events.append("original_NPC_idle_due_to_finite_personal_energy")
        return
    site=next((site for site in state["sites"] if
               _distance(npc["cell"],site["cell"])<=1),None)
    if site is None:
        events.append("original_NPC_cannot_act_outside_physical_home_range")
        return
    kind=None
    if npc["role"]=="caretaker":
        if npc["personal_supplies"]>=1 and site["integrity"]<config["site_integrity"]:
            npc["personal_supplies"]-=1
            site["integrity"]=min(config["site_integrity"],site["integrity"]+1)
            kind="help"
        elif site["stock"]>0:
            site["stock"]-=1;npc["cargo"]+=1
            kind="discover"
    elif npc["role"]=="scout" and site["stock"]>0:
        site["stock"]-=1;npc["cargo"]+=1;kind="discover"
    elif npc["role"]=="merchant":
        if config["npc_self_interest"] and site["integrity"]>0:
            site["integrity"]=max(0,site["integrity"]-1)
            kind="harm"
        elif site["stock"]>0:
            site["stock"]-=1;npc["cargo"]+=1;kind="discover"
    elif npc["role"]=="scribe":
        if npc["personal_supplies"]>=1 and site["integrity"]<config["site_integrity"]:
            npc["personal_supplies"]-=1
            site["integrity"]=min(config["site_integrity"],site["integrity"]+1)
            kind="repair"
        elif site["stock"]>0:
            site["stock"]-=1;npc["cargo"]+=1;kind="discover"
    if kind is None:
        events.append("original_NPC_had_no_remaining_legitimate_material_action")
        return
    npc["energy"]-=config["npc_action_energy_cost"]
    state["npc_events_generated"]+=1
    _emit(state,config,kind,site,events,actor="npc:"+str(npc["id"]))
    events.append("NPC_authored_role_drove_finite_physical_world_event")




def _npc_route(start,goals,blocked):
    """Shortest original grid route to a legal inspection/patrol tile."""
    pending=deque([start]);prior={start:None}
    goals=set(goals)
    while pending:
        cell=pending.popleft()
        if cell in goals:
            path=[]
            while cell!=start:
                path.append(cell)
                cell=prior[cell]
            path.reverse()
            return path
        for candidate in _neighbors(cell):
            if candidate not in blocked and candidate not in prior:
                prior[candidate]=cell
                pending.append(candidate)
    return None


def _npc_mobility_tick(state,config,events):
    """Actually walk a finite-energy NPC; forensic leads never become witnesses."""
    if not config["npc_mobility"] or not state["npcs"] or (
         state["npc_walks"]>=config["npc_walk_budget"]):
        return
    npc=state["npcs"][(state["tick"]//config["npc_patrol_interval"]-1)%
                       len(state["npcs"])]
    if npc["energy"]<config["npc_move_energy_cost"]:
        events.append("original_roaming_npc_exhausted_personal_energy")
        return
    lead=None
    if config["npc_pursues_evidence"]:
        for original in reversed(state["events_log"]):
            if original["id"] in npc["investigations"]:
                continue
            if (original["id"] not in
                [m["event_id"] for m in npc["memories"]] and
                _distance(npc["cell"],original["cell"])<=config["npc_lead_radius"]):
                lead=original
                break
    if lead is not None:
        target=lead["cell"]
    else:
        # Patrol alternating source districts, each with a physically
        # different original site, rather than teleporting to a target.
        district=(npc["id"]+state["day"]+1)%len(state["sites"])
        target=state["sites"][district]["cell"]
    if _distance(npc["cell"],target)<=1:
        if lead is not None:
            npc["investigations"].append(lead["id"])
            while len(npc["investigations"])>config["npc_investigation_memory"]:
                npc["investigations"].pop(0)
            entry={
                "tick":state["tick"],"npc_id":npc["id"],
                "event_id":lead["id"],"source_cell":target,
                "npc_cell":npc["cell"],
                "authority":"forensic_after_event_not_eyewitness",
            }
            state["forensic_edges"].append(entry)
            _remember(npc,lead,config,direct=False)
            events.append("original_npc_forensic_inspection_not_direct_witness")
        else:
            events.append("original_npc_reached_actual_patrol_district")
        return
    blocked=set(state["world"]["obstacles"])
    blocked.update(site["cell"] for site in state["sites"])
    blocked.update(other["cell"] for other in state["npcs"] if other is not npc)
    if config["npc_avoids_player"]:
        blocked.add(state["player"])
    goals=[cell for cell in _neighbors(target) if cell not in blocked]
    path=_npc_route(npc["cell"],goals,blocked)
    if not path:
        events.append("original_npc_route_physically_blocked")
        return
    destination=path[0]
    if _distance(npc["cell"],destination)!=1:
        raise QuestDirectorError("original NPC movement must follow adjacent real tiles")
    npc["cell"]=destination
    npc["energy"]-=config["npc_move_energy_cost"]
    npc["walks"]+=1
    state["npc_walks"]+=1
    events.append("original_npc_walked_real_adjacent_world_tile")

def _tick(state,config,events,steps=1):
    for _ in range(steps):
        state["tick"]+=1
        if state["tick"]%config["day_ticks"]==0:
            for npc in state["npcs"]:
                npc["energy"]=config["npc_energy"]
            state["day"]+=1
            events.append("actual_original_day_cycle_advanced")
        _rumors(state,config,events)
        if state["tick"]%config["npc_act_interval"]==0:
            _autonomous_npc_action(state,config,events)
        if state["tick"]%config["npc_patrol_interval"]==0:
            _npc_mobility_tick(state,config,events)
        if config["memory_decay_ticks"]>0:
            for npc in state["npcs"]:
                if state["tick"]%config["memory_decay_ticks"]==0:
                    for key in ("memories","heard"):
                        if npc[key]:
                            npc[key].pop(0)
                            events.append("old_original_npc_memory_naturally_decayed")
        for quest in state["quests"]:
            if quest["status"]=="active" and state["tick"]-quest["created_tick"]>=config["quest_ttl"]:
                quest["status"]="expired";quest["ending"]="unresolved"
                quest["resolution_tick"]=state["tick"]
                state["quest_archive"].append(quest["id"])
                events.append("witnessed_quest_expired_without_player_resolution")
    if (state["reputation"]<=-config["failure_reputation"] and
        config["ending_policy"]=="campaign"):
        state["failed"]=True;state["reason"]="actual_public_trust_collapse"


def step(state,config,action):
    if action not in ACTIONS:
        raise QuestDirectorError("unregistered original NPC quest action")
    if state["finished"] or state["failed"]:
        raise QuestDirectorError("terminal authored campaign cannot accept new moves")
    events=[]
    if action in ("north","south","east","west"):
        next_cell={
            "north":state["player"]-SIDE,
            "south":state["player"]+SIDE,
            "east":state["player"]+1,
            "west":state["player"]-1,
        }[action]
        old=state["player"]
        if (not 0<=next_cell<CELLS or _distance(old,next_cell)!=1
            or next_cell in state["world"]["obstacles"]):
            raise QuestDirectorError("physical player step is outside walkable original map")
        _spend(state,"stamina",config["movement_stamina"])
        state["player"]=next_cell
        state["discovered"]=sorted(set(state["discovered"])|{next_cell})
        events.append("original_player_walked_one_real_geographical_tile")
    elif action in ("inspect","wait","wait:4"):
        events.append("original_world_causes_observed_without_free_progress")
    elif action=="rest":
        state["stamina"]=min(config["stamina"],
                            state["stamina"]+config["rest_stamina"])
        events.append("finite_original_stamina_recovered_over_real_time")
    elif action.startswith(("help:","harm:","collect:","repair:")):
        kind,raw=action.split(":");site=_site(state,int(raw))
        if not _adjacent(state,site["cell"]):
            raise QuestDirectorError("quest event needs player physically near real world site")
        if kind=="help":
            _spend(state,"supplies",config["help_supplies"])
            _spend(state,"stamina",config["action_stamina"])
            site["integrity"]=min(config["site_integrity"],site["integrity"]+config["help_power"])
            _emit(state,config,"help",site,events)
        elif kind=="harm":
            _spend(state,"stamina",config["action_stamina"])
            if site["integrity"]<=0:
                raise QuestDirectorError("cannot destroy already destroyed original site")
            site["integrity"]=max(0,site["integrity"]-config["harm_power"])
            _emit(state,config,"harm",site,events)
        elif kind=="collect":
            _spend(state,"stamina",config["action_stamina"])
            if site["stock"]<config["gather_units"]:
                raise QuestDirectorError("original source deposit genuinely exhausted")
            site["stock"]-=config["gather_units"]
            state["supplies"]+=config["gather_units"]
            _emit(state,config,"discover",site,events)
        else:
            _spend(state,"supplies",config["repair_supplies"])
            _spend(state,"stamina",config["action_stamina"])
            if site["integrity"]>=config["site_integrity"]:
                raise QuestDirectorError("undamaged original landmark cannot be repaired")
            site["integrity"]=min(config["site_integrity"],
                                  site["integrity"]+config["repair_power"])
            _emit(state,config,"repair",site,events)
    elif action.startswith("speak:"):
        index=int(action.split(":")[1])
        if index>=len(state["npcs"]):
            raise QuestDirectorError("no original NPC is authored at this identifier")
        npc=state["npcs"][index]
        if not _adjacent(state,npc["cell"]):
            raise QuestDirectorError("cannot remotely interview an NPC that is not present")
        if (npc["trust"]<config["testimony_trust_floor"] or
            npc["suspicion"]>npc["trust"]+config["testimony_suspicion_tolerance"]):
            raise QuestDirectorError("NPC credibility cannot support first-hand testimony")
        found=False
        for quest in state["quests"]:
            if quest["status"]!="active" or npc["id"] in quest["testimonies"]:
                continue
            if any(m["event_id"]==quest["origin_event"] for m in npc["memories"]):
                quest["testimonies"].append(npc["id"])
                found=True
                events.append("original_direct_eyewitness_delivered_real_testimony")
            elif any(m["event_id"]==quest["origin_event"] for m in npc["heard"]):
                if npc["id"] not in quest["heard_from"]:
                    quest["heard_from"].append(npc["id"])
                    events.append("NPC_reported_rumor_without_eyewitness_authority")
                    found=True
        if not found:
            events.append("NPC_had_no_qualifying_original_eyewitness_information")
    elif action.startswith("choose:"):
        _,qid,branch=action.split(":")
        quest=next((q for q in state["quests"] if q["id"]==int(qid)),None)
        if quest is None or quest["status"]!="active":
            raise QuestDirectorError("choice requires real unresolved originating quest")
        if len(quest["testimonies"])<config["evidence_min"]:
            raise QuestDirectorError("rumor does not replace authentic local testimony")
        if quest["choice"] is not None:
            raise QuestDirectorError("cannot rewrite original committed outcome branch")
        quest["choice"]=branch
        events.append("original_quest_branch_committed_after_real_testimony")
    elif action.startswith("resolve:"):
        qid=int(action.split(":")[1])
        quest=next((q for q in state["quests"] if q["id"]==qid),None)
        if quest is None or quest["status"]!="active" or quest["choice"] is None:
            raise QuestDirectorError("only chosen active first-hand quest can resolve")
        site=_site(state,quest["site_id"])
        if not _adjacent(state,site["cell"]):
            raise QuestDirectorError("quest conclusion needs physical source-site presence")
        if (len(quest["testimonies"])<config["evidence_min"] or
            quest["material_actions"]<config["consequence_depth"]):
            raise QuestDirectorError("outcome requires corroboration and genuine followup acts")
        quest["status"]="resolved"
        quest["ending"]=("restored" if quest["choice"]=="support" else "exploited")
        quest["resolution_tick"]=state["tick"]
        state["quest_archive"].append(quest["id"])
        if quest["ending"]=="restored":
            state["quests_completed"]+=1
            state["gold"]+=config["reward_gold"]+(
                quest["rule_id"]%config["rule_bonus_modulus"])
            state["reputation"]=min(config["reputation_cap"],
                  state["reputation"]+config["reputation_gain"])
            events.append("real_original_evidence_based_support_resolution")
        else:
            state["quests_exploited"]+=1
            state["gold"]+=config["exploit_gold"]+(
                quest["rule_id"]%config["rule_bonus_modulus"])
            state["reputation"]=max(-config["reputation_cap"],
                  state["reputation"]-config["reputation_loss"])
            events.append("real_original_exploit_resolution_with_world_consequence")
        state["milestones"].append({
            "quest_id":qid,"site_id":site["id"],"ending":quest["ending"],
            "day":state["day"],"evidence":list(quest["testimonies"])
        })
        if state["quests_completed"]>=config["quest_goal"]:
            state["victory"]=True
            if config["ending_policy"]=="campaign" and not config["nonterminal_world"]:
                state["finished"]=True
                state["reason"]="actual_corrobated_witness_campaign_completed"
            else:
                state["reason"]="original_world_continues_after_witness_campaign"
            events.append("real_original_campaign_completion_condition_satisfied")
    else:
        raise QuestDirectorError("quest command lacks original world effect")
    _tick(state,config,events,4 if action=="wait:4" else 1)
    state["turn"]+=1
    state["events"]=events
    return events


def apply_verified_external_physical_incident(state,config,site_id,source_receipt,
                                             *,impact_severity=1):
    """Advance one visible external incident, never crediting the player.

    IMPORTANT: Caller must first *independently* verify the signed physical
    replay and its single attributable source collider. This is the strict
    world-side mutation primitive, not an external input verification gateway.
    """
    if state["finished"] or state["failed"]:
        raise QuestDirectorError("terminal quest world cannot accept new physical incidents")
    _integer(site_id,0,len(state["sites"])-1,"bound physical quest site")
    _integer(impact_severity,1,3,"bounded physical impact severity")
    if (type(source_receipt) is not dict or
        set(source_receipt)!={"interop_digest","source_editor","source_id"} or
        type(source_receipt["interop_digest"]) is not str or
        len(source_receipt["interop_digest"])!=64 or
        any(char not in "0123456789abcdef" for char in source_receipt["interop_digest"]) or
        source_receipt["source_editor"] not in ("platformer","racing","sandbox") or
        type(source_receipt["source_id"]) is not int):
        raise QuestDirectorError("signed external physical witness source identity required")
    site=_site(state,site_id)
    if site["integrity"]<=0:
        raise QuestDirectorError("already destroyed physical world site cannot be harmed again")
    site["integrity"]=max(0,site["integrity"]-impact_severity)
    events=[]
    proof=_emit(state,config,"harm",site,events,actor="external:physics",
                physical_source=source_receipt)
    _tick(state,config,events,1)
    state["turn"]+=1
    state["events"]=events
    return proof


__all__=["SIDE","CELLS","KINDS","ROLES","EVENTS","ACTIONS","QuestDirectorError",
         "default_layout","normalize_layout","start","apply_scene","step","apply_verified_external_physical_incident"]
