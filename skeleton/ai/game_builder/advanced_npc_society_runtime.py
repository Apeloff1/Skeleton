"""Deterministic original NPC society with bounded embodied residents.

Population totals are aggregated. Up to 32 residents are embodied; adaptive and
background LOD update far residents less often without faking memories. Social
evidence, proximity, work, hunger, law, trade and witness custody determine a
nonterminal community milestone. No generated dialogue claims model training.
"""
from __future__ import annotations

ACTIONS=("north","south","east","west","inspect","wait","observe","talk",
         "work","gather","donate","trade","help","accuse","mediate",
         "checkpoint","retire","rest")+tuple("focus:"+str(i) for i in range(16))
DIRS={"north":(0,1),"south":(0,-1),"east":(1,0),"west":(-1,0)}
PROFESSIONS=("farmer","builder","merchant","scholar","healer","guard")
SITE={"hall":[4,4],"market":[3,3],"farm":[1,5],
      "workshop":[6,5],"home":[1,1]}


class SocietyActionError(ValueError):
    """Unwitnessed social action, invalid original settlement or resource forgery."""


def _int(v,lo,hi,name):
    if type(v) is not int or not lo<=v<=hi:
        raise SocietyActionError("invalid society "+name)
    return v


def _point(point,name):
    if type(point) is not list or len(point)!=2:
        raise SocietyActionError("exact original settlement point required: "+name)
    return [_int(point[0],0,8,name+" x"),_int(point[1],0,8,name+" y")]


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    return {
        "title":"Original Living Borough "+str(seed%1000),
        "start":[1,1],"sites":{k:list(v) for k,v in SITE.items()},
        "witnesses":[
            {"id":0,"role":"farmer","home":[1,1],"work":[1,5],"faction":"village"},
            {"id":1,"role":"builder","home":[2,1],"work":[6,5],"faction":"guild"},
            {"id":2,"role":"merchant","home":[3,1],"work":[3,3],"faction":"guild"},
        ],
        "incident":"granary_dispute",
        "season":("spring","summer","autumn","winter")[seed%4],
        "world_terminal":False,
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","start","sites","witnesses","incident","season","world_terminal"
    }:
        raise SocietyActionError("strict authored social-world schema required")
    name=layout["title"]
    if type(name) is not str or not 3<=len(name)<=64 or not all(
        c.isalnum() or c in " _-" for c in name
    ):
        raise SocietyActionError("unsafe original settlement label")
    if _point(layout["start"],"start")!=[1,1]:
        raise SocietyActionError("original citizen's starting position is immutable")
    sites=layout["sites"]
    if type(sites) is not dict or set(sites)!=set(SITE):
        raise SocietyActionError("exact reviewed settlement services required")
    safe={}
    for k,p in SITE.items():
        if _point(sites[k],"site "+k)!=p:
            raise SocietyActionError("authored social venue may not bypass walking")
        safe[k]=list(p)
    people=layout["witnesses"]
    if type(people) is not list or len(people)!=3:
        raise SocietyActionError("three original witnesses are required")
    expected=(("farmer","village","farm"),
              ("builder","guild","workshop"),("merchant","guild","market"))
    normalized=[]
    for i,p in enumerate(people):
        if type(p) is not dict or set(p)!={"id","role","home","work","faction"}:
            raise SocietyActionError("witness needs exact role, address and faction")
        role,faction,job=expected[i]
        if type(p["id"]) is not int or p["id"]!=i or (
            p["role"]!=role or p["faction"]!=faction
        ):
            raise SocietyActionError("original witness identity is source-protected")
        home=[1+i,1]
        if _point(p["home"],"witness home")!=home or (
            _point(p["work"],"witness job")!=safe[job]
        ):
            raise SocietyActionError("witness occupation and home cannot teleport")
        normalized.append({"id":i,"role":role,"home":home,
                           "work":list(safe[job]),"faction":faction})
    if type(layout["incident"]) is not str or layout["incident"]!="granary_dispute":
        raise SocietyActionError("no untrusted invented narrative event is executable")
    if type(layout["season"]) is not str or layout["season"] not in (
        "spring","summer","autumn","winter"
    ):
        raise SocietyActionError("unknown authored season")
    if layout["world_terminal"] is not False:
        raise SocietyActionError("citizen worlds remain playable after celebration")
    return {"title":name,"start":[1,1],"sites":safe,"witnesses":normalized,
            "incident":"granary_dispute","season":layout["season"],
            "world_terminal":False}


def start(config,seed):
    scene=normalize_layout(config,default_layout(config,seed))
    residents=[]
    count=min(config["population"],config["active_npcs"],32)
    for i in range(count):
        witness=scene["witnesses"][i] if i<3 else None
        profession=(witness["role"] if witness else
                    PROFESSIONS[(i+seed)%len(PROFESSIONS)])
        home=list(witness["home"] if witness else [1+i%7,1+(i//7)%2])
        work=list(witness["work"] if witness else (
            SITE["farm"] if profession=="farmer" else
            SITE["market"] if profession=="merchant" else SITE["workshop"]
        ))
        residents.append({
            "id":i,"role":profession,"home":home,"work":work,
            "position":list(home),"needs":{"hunger":0,"fatigue":0},
            "bond":0,"wellbeing":70,"tasks_completed":0,
            "faction":witness["faction"] if witness else
                      ("village" if i%2==0 else "guild"),
            "last_update":0,
        })
    return {
        "tick":0,"title":scene["title"],"season":scene["season"],
        "position":[1,1],"sites":scene["sites"],"residents":residents,
        "population":config["population"],"background_population":
            max(0,config["population"]-len(residents)),
        "embodied":len(residents),"focus":0 if residents else None,
        "food":config["initial_food"],"materials":config["initial_materials"],
        "gold":config["initial_gold"],"player_energy":config["player_energy"],
        "trust":0,"stability":50,"unrest":0,"productivity":0,
        "relations":[],"evidence":[],"memories":[],
        "witnesses":scene["witnesses"],"incident":scene["incident"],
        "incident_resolved":False,"community_checkpoint":False,
        "background_batches":0,"full_updates":0,"coarse_updates":0,
        "festival_count":0,"retired":False,"finished":False,"failed":False,
        "events":[],
    }


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise SocietyActionError("cannot replace active living society source")
    state["title"]=source["title"]
    state["season"]=source["season"]
    state["position"]=list(source["start"])
    state["sites"]={k:list(v) for k,v in source["sites"].items()}
    state["witnesses"]=[{**p,"home":list(p["home"]),"work":list(p["work"])}
                        for p in source["witnesses"]]


def _near(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])<=1


def _memory(state,config,who,kind,proof):
    entry={"tick":state["tick"],"resident":who,"kind":kind,"proof":proof}
    state["memories"].append(entry)
    if len(state["memories"])>config["memory_records"]:
        state["memories"]=state["memories"][-config["memory_records"]:] if (
            config["memory_records"]
        ) else []
    return entry


def _focus(state):
    who=state["focus"]
    return next((r for r in state["residents"] if r["id"]==who),None)


def _daily_cycle(state,config):
    if not state["residents"]:return
    for resident in state["residents"]:
        distance=abs(resident["position"][0]-state["position"][0])+abs(
            resident["position"][1]-state["position"][1]
        )
        full=(config["simulation_lod"]=="full" or
              (config["simulation_lod"]=="adaptive" and distance<=config["focus_radius"]) or
              state["tick"]%config["coarse_period"]==0)
        if not full:continue
        elapsed=max(1,state["tick"]-resident["last_update"])
        resident["last_update"]=state["tick"]
        needs=resident["needs"]
        needs["hunger"]=min(100,needs["hunger"]+elapsed*config["hunger_rate"])
        needs["fatigue"]=min(100,needs["fatigue"]+elapsed*config["fatigue_rate"])
        # Time-of-day movement never teleports; one traversable step toward a
        # reviewed home/work venue is performed for each simulation update.
        target=resident["work"] if state["tick"]%config["day_length"]<(
            config["day_length"]//2
        ) else resident["home"]
        dx=target[0]-resident["position"][0]
        dy=target[1]-resident["position"][1]
        if dx:resident["position"][0]+=1 if dx>0 else -1
        elif dy:resident["position"][1]+=1 if dy>0 else -1
        if needs["hunger"]>=config["meal_threshold"] and state["food"]>0:
            state["food"]-=1
            needs["hunger"]=max(0,needs["hunger"]-config["meal_relief"])
        if resident["position"]==resident["work"] and needs["fatigue"]<80:
            if resident["role"]=="farmer":
                state["food"]=min(config["food_capacity"],state["food"]+1)
            elif resident["role"] in ("builder","merchant"):
                state["materials"]=min(config["material_capacity"],
                                       state["materials"]+1)
            resident["tasks_completed"]+=1
            state["productivity"]+=1
        if resident["position"]==resident["home"]:
            needs["fatigue"]=max(0,needs["fatigue"]-config["rest_relief"])
        resident["wellbeing"]=max(0,min(100,80-needs["hunger"]//2-
                                       needs["fatigue"]//3+resident["bond"]//4))
        state["full_updates" if elapsed==1 else "coarse_updates"]+=1
    if (state["background_population"] and
        state["tick"]%config["coarse_period"]==0):
        state["background_batches"]+=1
        workers=max(1,state["background_population"]//config["background_cohort"])
        state["food"]=min(config["food_capacity"],state["food"]+workers)
        # Abstract cohorts consume upkeep rather than minting unlimited goods.
        state["food"]=max(0,state["food"]-workers//2)
    if state["food"]==0:
        state["unrest"]=min(100,state["unrest"]+config["scarcity_unrest"])
    else:
        state["unrest"]=max(0,state["unrest"]-1)
    state["stability"]=max(0,min(100,50+state["trust"]-state["unrest"]))


def step(state,config,action):
    if action not in ACTIONS:
        raise SocietyActionError("unknown original settlement command")
    if state["failed"] or state["finished"]:
        raise SocietyActionError("a retired society session cannot advance")
    events=[]
    if action in DIRS:
        dx,dy=DIRS[action]
        point=[state["position"][0]+dx,state["position"][1]+dy]
        if not 0<=point[0]<=8 or not 0<=point[1]<=8:
            events.append("bounded_original_settlement_path")
        elif state["player_energy"]<=0:
            raise SocietyActionError("town movement requires real player stamina")
        else:
            state["position"]=point
            state["player_energy"]-=1
            events.append("citizen_moved_through_original_town")
    elif action.startswith("focus:"):
        target=int(action.split(":")[1])
        if target>=state["embodied"]:
            raise SocietyActionError("cannot invent a non-resident NPC witness")
        state["focus"]=target
        events.append("source_bound_citizen_selected")
    elif action=="rest":
        if state["position"]!=state["sites"]["home"]:
            raise SocietyActionError("player must return to original home to rest")
        state["player_energy"]=min(config["player_energy"],
                                   state["player_energy"]+config["rest_energy"])
        events.append("finite_citizen_energy_recovered")
    elif action in ("talk","observe","help","trade","accuse"):
        r=_focus(state)
        if r is None or not _near(state["position"],r["position"]):
            raise SocietyActionError("witnessed social action requires physical NPC presence")
        if action=="talk":
            r["bond"]=min(100,r["bond"]+config["dialogue_bond"])
            _memory(state,config,r["id"],"conversation","direct_proximity")
            state["trust"]+=1
            events.append("witnessed_social_conversation")
        elif action=="observe":
            token="observed_resident_"+str(r["id"])
            if token not in state["evidence"]:
                state["evidence"].append(token)
            _memory(state,config,r["id"],"observation",token)
            events.append("direct_citizen_observation")
        elif action=="help":
            if state["food"]<config["help_food"]:
                raise SocietyActionError("help requires conserved town food stock")
            state["food"]-=config["help_food"]
            r["needs"]["hunger"]=max(0,r["needs"]["hunger"]-config["meal_relief"])
            r["bond"]=min(100,r["bond"]+config["help_bond"])
            state["trust"]+=2
            _memory(state,config,r["id"],"assistance","food_inventory")
            events.append("finite_neighbor_assistance")
        elif action=="trade":
            if state["gold"]<config["trade_cost"] or state["materials"]<1:
                raise SocietyActionError("trade needs both money and real goods")
            state["gold"]-=config["trade_cost"];state["materials"]-=1
            state["food"]=min(config["food_capacity"],state["food"]+config["trade_food"])
            r["bond"]=min(100,r["bond"]+1)
            _memory(state,config,r["id"],"exchange","paid_goods_and_gold")
            events.append("real_local_market_exchange")
        elif action=="accuse":
            token="observed_resident_"+str(r["id"])
            if token not in state["evidence"]:
                raise SocietyActionError("lawful accusation requires direct evidence")
            r["bond"]=max(-100,r["bond"]-config["accusation_penalty"])
            state["trust"]-=config["accusation_penalty"]//2
            _memory(state,config,r["id"],"allegation",token)
            events.append("evidenced_accusation_with_social_cost")
    elif action=="gather":
        if state["position"]!=state["sites"]["farm"]:
            raise SocietyActionError("food gathering requires original farm location")
        if state["player_energy"]<config["work_energy"]:
            raise SocietyActionError("player is too exhausted for farm labor")
        state["player_energy"]-=config["work_energy"]
        state["food"]=min(config["food_capacity"],state["food"]+config["farm_yield"])
        events.append("finite_player_farm_harvest")
    elif action=="work":
        if state["position"]!=state["sites"]["workshop"]:
            raise SocietyActionError("manufacturing requires original town workshop")
        if state["player_energy"]<config["work_energy"]:
            raise SocietyActionError("actual crafting labor needs stamina")
        state["player_energy"]-=config["work_energy"]
        state["materials"]=min(config["material_capacity"],
                               state["materials"]+config["work_yield"])
        events.append("player_work_generated_bounded_materials")
    elif action=="donate":
        if state["position"]!=state["sites"]["market"] or (
            state["gold"]<config["donation_gold"]
        ):
            raise SocietyActionError("public donations need actual market and gold")
        state["gold"]-=config["donation_gold"]
        state["trust"]+=config["donation_trust"]
        events.append("witnessed_public_funds_donated")
    elif action=="mediate":
        if state["position"]!=state["sites"]["hall"]:
            raise SocietyActionError("mediation requires original civic hall")
        if not all("observed_resident_"+str(i) in state["evidence"] for i in (0,1)):
            raise SocietyActionError("two independent witnessed accounts required")
        if state["incident_resolved"]:
            raise SocietyActionError("a resolved dispute cannot mint duplicate trust")
        state["incident_resolved"]=True
        state["trust"]+=config["mediation_trust"]
        _memory(state,config,-1,"civic_mediation","two_direct_witnesses")
        events.append("two_witness_civic_dispute_resolved")
    elif action=="checkpoint":
        if state["position"]!=state["sites"]["hall"] or (
            not state["incident_resolved"] or
            state["trust"]<config["checkpoint_trust"] or
            state["food"]<config["checkpoint_food"] or state["community_checkpoint"]
        ):
            raise SocietyActionError("earned community milestone prerequisites absent")
        state["community_checkpoint"]=True
        state["festival_count"]+=1
        events.append("nonterminal_living_town_milestone")
    elif action=="retire":
        if not state["community_checkpoint"] or state["position"]!=state["sites"]["home"]:
            raise SocietyActionError("optional retirement needs completed civic work and home")
        state["finished"]=state["retired"]=True
        events.append("voluntary_citizen_retirement")
    state["tick"]+=1
    _daily_cycle(state,config)
    if state["tick"]>=config["turn_limit"]:
        state["failed"]=True
        events.append("bounded_society_rehearsal_exhausted")
    state["events"]=events
    return events
