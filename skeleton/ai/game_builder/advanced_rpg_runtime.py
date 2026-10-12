"""Original, deterministic RPG: spatial quests, witnessed NPC choices and party progression.

Playable advanced reference with encounter damage, recoverable equipment, quest
evidence, persistent post-story exploration, class tactics and replayed history.
No provider model, licensed content, copyrighted dialogue or untrusted scripts.
"""
from __future__ import annotations

CLASSES=("guardian","scholar","scout","mender")
ACTIONS=("north","south","east","west","inspect","talk","negotiate",
         "investigate","accept","gather","attack","cast","guard","heal",
         "camp","craft","equip","turn_in","finish","retire",
         "choose:trust","choose:challenge","choose:trade")+tuple(
             "select:"+str(i) for i in range(16))
MOVES={"north":(0,1),"south":(0,-1),"east":(1,0),"west":(-1,0)}
QUESTS=("recover_relic","resolve_dispute","clear_threat")


class RPGActionError(ValueError):
    """A source, party action or evidence-bound quest transition was rejected."""


def _int(v,lo,hi,name):
    if type(v) is not int or not lo<=v<=hi:
        raise RPGActionError("invalid original RPG "+name)
    return v


def _point(point,config,name):
    if type(point) is not list or len(point)!=2:
        raise RPGActionError("exact original world coordinate required: "+name)
    return [_int(point[0],0,config["world_width"]-1,name+" x"),
            _int(point[1],0,config["world_height"]-1,name+" y")]


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    w,h=config["world_width"],config["world_height"]
    return {
        "title":"Original Wayfarer Chronicle "+str(seed%1000),
        "climate":("temperate","rain","frost")[seed%3],
        "start":[0,0],"exit":[w-2,h-2],
        "npcs":[
            {"id":0,"role":"archivist","at":[1,1],"faction":"guild"},
            {"id":1,"role":"mediator","at":[2,h-3],"faction":"village"},
        ],
        "relic":[w//2,1],"enemy":[w//2,3],
        "enemy_hp":config["enemy_health"],"enemy_type":("beast","bandit","construct")[seed%3],
        "blocked":[[w//2,2],[w//2+1,2]],
        "quests":list(QUESTS),
        "camp":[0,h-2],
        "story_open":True,
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","climate","start","exit","npcs","relic","enemy","enemy_hp",
        "enemy_type","blocked","quests","camp","story_open",
    }:
        raise RPGActionError("reviewed original RPG world requires exact schema")
    name=layout["title"]
    if type(name) is not str or not 3<=len(name)<=64 or not all(
        ch.isalnum() or ch in " _-" for ch in name
    ):
        raise RPGActionError("unsafe authored role-playing world title")
    if type(layout["climate"]) is not str or layout["climate"] not in (
        "temperate","rain","frost"
    ):
        raise RPGActionError("unreviewed RPG climate")
    if type(layout["enemy_type"]) is not str or layout["enemy_type"] not in (
        "beast","bandit","construct"
    ):
        raise RPGActionError("unreviewed original monster class")
    start=_point(layout["start"],config,"start")
    exit_at=_point(layout["exit"],config,"exit")
    if start!=[0,0] or exit_at!=[config["world_width"]-2,config["world_height"]-2]:
        raise RPGActionError("world origin/exit cannot bypass authored story route")
    relic=_point(layout["relic"],config,"relic")
    foe=_point(layout["enemy"],config,"enemy")
    camp=_point(layout["camp"],config,"camp")
    if len({tuple(a) for a in (start,exit_at,relic,foe,camp)})!=5:
        raise RPGActionError("quests must occupy distinct physical world cells")
    if _int(layout["enemy_hp"],1,config["enemy_health"],"encounter HP")!=config["enemy_health"]:
        raise RPGActionError("authored encounter cannot reduce real enemy budget")
    raw=layout["npcs"]
    if type(raw) is not list or len(raw)!=2:
        raise RPGActionError("a reviewed RPG requires two independently witnessed NPCs")
    people=[]
    for i,person in enumerate(raw):
        if type(person) is not dict or set(person)!={"id","role","at","faction"}:
            raise RPGActionError("exact NPC identity, dialogue role and faction required")
        if type(person["id"]) is not int or person["id"]!=i:
            raise RPGActionError("original NPC witness identity is immutable")
        role=("archivist","mediator")[i]
        faction=("guild","village")[i]
        if person["role"]!=role or person["faction"]!=faction:
            raise RPGActionError("NPC role cannot evade quest/faction custody")
        at=_point(person["at"],config,"NPC location")
        if at in (start,exit_at,relic,foe,camp):
            raise RPGActionError("NPC overlaps authored objective")
        people.append({"id":i,"role":role,"at":at,"faction":faction})
    if people[0]["at"]==people[1]["at"]:
        raise RPGActionError("distinct NPC witnesses cannot overlap")
    blocks=layout["blocked"]
    if type(blocks) is not list or len(blocks)>config["max_obstacles"]:
        raise RPGActionError("bounded authored RPG obstacles required")
    occupied={tuple(p) for p in (start,exit_at,relic,foe,camp)}
    occupied.update(tuple(p["at"]) for p in people)
    walls=[]
    for cell in blocks:
        at=_point(cell,config,"obstacle")
        if tuple(at) in occupied:
            raise RPGActionError("wall overlaps source objective or another wall")
        occupied.add(tuple(at));walls.append(at)
    if type(layout["quests"]) is not list or layout["quests"]!=list(QUESTS):
        raise RPGActionError("quest structure cannot be replaced with untrusted branches")
    if type(layout["story_open"]) is not bool or not layout["story_open"]:
        raise RPGActionError("original world must retain player choice agency")
    return {
        "title":name,"climate":layout["climate"],"start":start,"exit":exit_at,
        "npcs":people,"relic":relic,"enemy":foe,
        "enemy_hp":config["enemy_health"],"enemy_type":layout["enemy_type"],
        "blocked":walls,"quests":list(QUESTS),"camp":camp,"story_open":True,
    }


def start(config,seed):
    level=normalize_layout(config,default_layout(config,seed))
    party=[
        {"id":i,"class":CLASSES[i%len(CLASSES)],
         "level":1,"xp":0,"hp":config["hero_health"],"mana":config["hero_mana"],
         "guard":0,"injuries":0} for i in range(config["party_size"])
    ]
    return {
        "tick":0,"title":level["title"],"climate":level["climate"],
        "position":level["start"],"exit":level["exit"],"npcs":level["npcs"],
        "relic":level["relic"],"enemy":level["enemy"],"enemy_hp":level["enemy_hp"],
        "enemy_type":level["enemy_type"],"blocked":level["blocked"],"camp":level["camp"],
        "party":party,"selected":0,
        "quests":{q:"available" for q in QUESTS},
        "quest_relic":False,"quest_dispute":False,"quest_threat":False,
        "evidence":[],"social_memories":[],
        "factions":{"guild":0,"village":0},
        "inventory":{"herbs":config["starting_herbs"],"ore":0,
                     "relic":0,"potions":config["starting_potions"],
                     "supplies":config["camp_supplies"]},
        "gold":config["starting_gold"],"gear":0,"crafted":0,
        "dialogue_turns":0,"battles":0,"chapters_completed":0,
        "chapter_claimed":False,"postgame_steps":0,"score":0,
        "finished":False,"failed":False,"events":[],
    }


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise RPGActionError("cannot replace a running persistent authored story")
    for k in ("title","climate","exit","npcs","relic","enemy","enemy_hp",
              "enemy_type","blocked","camp"):
        v=source[k]
        if k=="npcs":state[k]=[{**p,"at":list(p["at"])} for p in v]
        elif k=="blocked":state[k]=[list(p) for p in v]
        elif k in ("exit","relic","enemy","camp"):state[k]=list(v)
        else:state[k]=v
    state["position"]=list(source["start"])


def _distance(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])


def _near(a,b):
    return _distance(a,b)<=1


def _award(state,config,points):
    for hero in state["party"]:
        if hero["hp"]<=0:continue
        hero["xp"]+=points
        while hero["level"]<config["level_cap"] and hero["xp"]>=(
            hero["level"]*config["xp_per_level"]
        ):
            hero["xp"]-=hero["level"]*config["xp_per_level"]
            hero["level"]+=1
            hero["hp"]=min(config["hero_health"],hero["hp"]+config["level_heal"])
            hero["mana"]=min(config["hero_mana"],hero["mana"]+config["level_mana"])
    state["score"]+=points


def step(state,config,action):
    if action not in ACTIONS:
        raise RPGActionError("unknown original party/world command")
    if state["finished"] or state["failed"]:
        raise RPGActionError("cannot alter a terminated role-playing session")
    selected=state["party"][state["selected"]]
    events=[]
    if action.startswith("select:"):
        i=int(action.split(":")[1])
        if i>=len(state["party"]) or state["party"][i]["hp"]<=0:
            raise RPGActionError("selected party member must be present and conscious")
        state["selected"]=i
        selected=state["party"][i]
        events.append("physical_party_role_changed")
    elif action in MOVES:
        dx,dy=MOVES[action]
        pos=[state["position"][0]+dx,state["position"][1]+dy]
        if not (0<=pos[0]<config["world_width"] and
                0<=pos[1]<config["world_height"]) or pos in state["blocked"]:
            events.append("authored_world_collision")
        elif selected["hp"]<=0:
            raise RPGActionError("unconscious party cannot traverse an encounter")
        else:
            state["position"]=pos
            if state["chapter_claimed"]:state["postgame_steps"]+=1
            events.append("persistent_world_traversal")
    elif action=="accept":
        if not any(_near(state["position"],p["at"]) for p in state["npcs"]):
            raise RPGActionError("quests must be accepted from a physical NPC")
        for q in QUESTS:
            if state["quests"][q]=="available":state["quests"][q]="active"
        events.append("witnessed_quest_acceptance")
    elif action=="talk":
        near=[p for p in state["npcs"] if _near(state["position"],p["at"])]
        if not near:raise RPGActionError("NPC dialogue requires presence in world")
        witness=near[0]
        state["dialogue_turns"]+=1
        state["social_memories"].append({
            "tick":state["tick"],"npc":witness["id"],
            "subject":"quest" if any(v=="active" for v in state["quests"].values())
                      else "uncommitted_world",
        })
        events.append("direct_npc_conversation_recorded")
    elif action=="investigate":
        if not _near(state["position"],state["relic"]):
            raise RPGActionError("quest evidence requires spatial investigation")
        if "ruin_survey" not in state["evidence"]:
            state["evidence"].append("ruin_survey")
        events.append("physical_ruins_evidence_discovered")
    elif action.startswith("choose:") or action=="negotiate":
        person=state["npcs"][1]
        if not _near(state["position"],person["at"]):
            raise RPGActionError("social choices require the mediator as witness")
        if state["quests"]["resolve_dispute"]!="active":
            raise RPGActionError("dispute dialogue requires accepted active quest")
        if "ruin_survey" not in state["evidence"]:
            raise RPGActionError("a source-witnessed piece of evidence is required")
        kind=action.split(":")[-1] if action.startswith("choose:") else "trust"
        delta={"trust":3,"challenge":-2,"trade":2}[kind]
        if kind=="trade":
            if state["gold"]<config["diplomacy_cost"]:
                raise RPGActionError("a peaceful trade cannot mint finite gold")
            state["gold"]-=config["diplomacy_cost"]
        state["factions"]["village"]+=delta
        state["social_memories"].append({
            "tick":state["tick"],"npc":1,"subject":kind,
            "evidence":"ruin_survey",
        })
        state["quest_dispute"]=True
        events.append("consequential_witnessed_social_choice")
    elif action=="gather":
        if state["position"]==state["relic"]:
            if state["quests"]["recover_relic"]!="active":
                raise RPGActionError("relic retrieval requires an accepted quest")
            if state["inventory"]["relic"]:
                raise RPGActionError("cannot harvest one relic twice")
            state["inventory"]["relic"]=1;state["quest_relic"]=True
            events.append("unique_authored_quest_relic_found")
        elif state["position"]==state["camp"]:
            if state["inventory"]["herbs"]>=config["herb_capacity"]:
                raise RPGActionError("finite original forage supply is full")
            state["inventory"]["herbs"]+=1
            events.append("herb_foraged_at_original_camp")
        else:raise RPGActionError("resource extraction requires an authored world site")
    elif action in ("attack","cast"):
        if not _near(state["position"],state["enemy"]) or state["enemy_hp"]<=0:
            raise RPGActionError("combat requires a live local authored enemy")
        if selected["hp"]<=0:
            raise RPGActionError("unconscious hero cannot fight")
        if action=="cast":
            if selected["mana"]<config["spell_cost"]:
                raise RPGActionError("spells consume real available mana")
            selected["mana"]-=config["spell_cost"]
            damage=config["spell_damage"]+selected["level"]
        else:
            damage=config["attack_damage"]+selected["level"]+state["gear"]*2
        state["enemy_hp"]=max(0,state["enemy_hp"]-damage)
        events.append("spatial_party_damage")
        if state["enemy_hp"]==0:
            state["quest_threat"]=True
            state["battles"]+=1
            _award(state,config,config["combat_xp"])
            events.append("witnessed_encounter_defeated")
    elif action=="guard":
        selected["guard"]=config["guard_block"]
        events.append("party_guard_readied")
    elif action=="heal":
        if state["inventory"]["potions"]<=0:
            raise RPGActionError("healing requires a finite original potion")
        if selected["hp"]>=config["hero_health"]:
            raise RPGActionError("cannot spend potion on an uninjured hero")
        state["inventory"]["potions"]-=1
        selected["hp"]=min(config["hero_health"],
                           selected["hp"]+config["potion_healing"])
        events.append("finite_party_healing")
    elif action=="camp":
        if state["position"]!=state["camp"] or state["inventory"]["supplies"]<=0:
            raise RPGActionError("camp must be occupied and consume finite supplies")
        state["inventory"]["supplies"]-=1
        for hero in state["party"]:
            if hero["hp"]>0:
                hero["hp"]=min(config["hero_health"],hero["hp"]+config["camp_healing"])
                hero["mana"]=min(config["hero_mana"],hero["mana"]+config["camp_mana"])
        events.append("finite_resting_supplies_consumed")
    elif action=="craft":
        if state["position"]!=state["camp"] or state["inventory"]["herbs"]<2:
            raise RPGActionError("crafting requires original camp and consumed herbs")
        state["inventory"]["herbs"]-=2
        state["inventory"]["potions"]+=1
        state["crafted"]+=1
        events.append("herbs_converted_into_one_potion")
    elif action=="equip":
        if state["position"]!=state["camp"] or state["gold"]<config["gear_cost"]:
            raise RPGActionError("gear upgrade requires authored camp and finite gold")
        if state["gear"]>=config["max_gear"]:
            raise RPGActionError("party equipment upgrade ceiling reached")
        state["gold"]-=config["gear_cost"]
        state["gear"]+=1
        events.append("permanent_finite_gear_upgrade")
    elif action=="turn_in":
        if not _near(state["position"],state["npcs"][0]["at"]):
            raise RPGActionError("quest rewards require direct guild witness")
        candidates=(
            ("recover_relic",state["quest_relic"]),
            ("resolve_dispute",state["quest_dispute"]),
            ("clear_threat",state["quest_threat"]),
        )
        found=False
        for q,done in candidates:
            if done and state["quests"][q]=="active":
                state["quests"][q]="completed"
                state["gold"]+=config["quest_gold_reward"]
                state["factions"]["guild"]+=2
                _award(state,config,config["quest_xp"])
                events.append("earned_quest_reward_"+q)
                found=True
        if not found:
            raise RPGActionError("quest reward cannot be claimed without completion")
    elif action=="finish":
        if state["position"]!=state["exit"] or not all(
            status=="completed" for status in state["quests"].values()
        ) or state["chapter_claimed"]:
            raise RPGActionError("world ending requires all earned quests and real exit")
        state["chapters_completed"]+=1
        state["chapter_claimed"]=True
        state["score"]+=config["chapter_bonus"]
        if not config["persistent_world"]:
            state["finished"]=True
        events.append("earned_chapter_completion")
        if config["persistent_world"]:
            events.append("nonterminal_postgame_world_unlocked")
    elif action=="retire":
        if not state["chapter_claimed"]:
            raise RPGActionError("retirement requires an independently earned chapter")
        state["finished"]=True;events.append("player_chose_world_retirement")
    # The physical opponent threatens any nearby party during a tick.
    if state["enemy_hp"]>0 and _near(state["position"],state["enemy"]):
        target=state["party"][state["selected"]]
        if target["hp"]>0:
            mitigated=max(0,config["enemy_damage"]-target["guard"])
            target["hp"]=max(0,target["hp"]-mitigated)
            target["guard"]=0
            if mitigated:events.append("enemy_counterattack_damage")
    state["tick"]+=1
    if all(p["hp"]==0 for p in state["party"]) or state["tick"]>=config["turn_limit"]:
        state["failed"]=True;events.append("party_exhausted_or_time_limit")
    state["events"]=events
    return events
