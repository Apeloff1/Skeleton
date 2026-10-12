"""Unified original NPC world: one authoritative position, clock and event bus.

Unlike the earlier three independently replayed settings, this world gives each
resident one physical body and one state record. Dialogue, witness-triggered
quests and social assistance operate against the SAME coordinates, schedules,
inventory and monotonic event ledger. Existing authored scenes supply source
roles and design constraints; we do not execute/synchronize their separate
runtime instances or present those coordinates as identical by assertion.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json

from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.original_unified_npc_world.v1"
SIDE = 7
MAX_COMMANDS = 96
MAX_BYTES = 280_000
ORDER = ("player_action", "witness_commit", "schedule_advance", "world_receipt")
MOVES = {"north": -SIDE, "south": SIDE, "east": 1, "west": -1}
ACTOR_PREFIX = "original_npc:"
ACTIONS = ("inspect", "wait", "rest", "retire") + tuple(
    f"{kind}:{i}"
    for kind in ("speak", "support", "observe", "discover", "help", "harm",
                 "followup", "resolve", "council")
    for i in range(4)
) + tuple("move:" + k for k in MOVES)


class UnifiedWorldError(ValueError):
    """Invalid source, non-physical action, fake eyewitness or forged receipt."""


def _serialized(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise UnifiedWorldError("original unified state requires canonical safe JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise UnifiedWorldError("original unified world exceeds bounded evidence capacity")
    return encoded


def _hash(value):
    return sha256(_serialized(value).encode("utf-8")).hexdigest()


def _distance(a, b):
    return abs(a % SIDE-b % SIDE)+abs(a//SIDE-b//SIDE)


def _neighbors(c):
    x,y=c%SIDE,c//SIDE
    for nx,ny in ((x,y-1),(x-1,y),(x+1,y),(x,y+1)):
        if 0<=nx<SIDE and 0<=ny<SIDE:
            yield nx+SIDE*ny


def _sight(a, b, blockers):
    """Grid sight with occlusion; a blocking corner cannot attest by rumor."""
    x0,y0=a%SIDE,a//SIDE
    x1,y1=b%SIDE,b//SIDE
    dx=abs(x1-x0);dy=abs(y1-y0)
    sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1
    err=dx-dy
    while x0!=x1 or y0!=y1:
        e=2*err
        if e>-dy:
            err-=dy;x0+=sx
        if e<dx:
            err+=dx;y0+=sy
        at=x0+SIDE*y0
        if at in blockers and at!=b:
            return False
    return True


def _step_toward(source, target, blockers, occupied):
    """BFS for a SINGLE actual tile of movement, never target teleportation."""
    if source==target:
        return source
    queue=deque([source]);first={source:source}
    while queue:
        current=queue.popleft()
        for nxt in _neighbors(current):
            if nxt in first or nxt in blockers or (nxt in occupied and nxt!=target):
                continue
            first[nxt] = nxt if current==source else first[current]
            if nxt==target:
                candidate=first[nxt]
                return source if candidate in occupied else candidate
            queue.append(nxt)
    return source


def _sources(settings, scenes, seed):
    if type(seed) is not int or not 0<=seed<=2**31-1:
        raise UnifiedWorldError("bounded source seed is required")
    if settings is None:settings={}
    if scenes is None:scenes={}
    if type(settings) is not dict or type(scenes) is not dict or (
        set(settings)-{"quest_director","dialogue","npc_society"}
        or set(scenes)-{"quest_director","dialogue","npc_society"}
    ):
        raise UnifiedWorldError("only three exact original source families are authorized")
    config={};source={};links={}
    for name in ("quest_director","dialogue","npc_society"):
        rules=make_editor_document(name,settings.get(name))
        config[name]=rules["settings"]
        document=(validate_advanced_scene(scenes[name],rules["settings"])
                  if name in scenes else
                  make_advanced_scene(name,rules["settings"],seed=seed))
        if document["seed"]!=seed or document["editor"]!=name:
            raise UnifiedWorldError("world sources must bind one exact authored seed")
        source[name]=document
        links[name]={"settings_digest":rules["digest"],
                     "source_scene_digest":document["digest"]}
    return config,source,links


def _initial(config,scenes):
    q=scenes["quest_director"]["layout"]
    d=scenes["dialogue"]["layout"]
    n=scenes["npc_society"]["layout"]
    if q["width"]!=SIDE or q["height"]!=SIDE:
        raise UnifiedWorldError("single canonical NPC world requires a 7x7 source map")
    actors=[]
    for datum in q["npcs"]:
        i=datum["id"]
        alias=(d["speakers"][i] if i<len(d["speakers"]) else None)
        citizen=(n["witnesses"][i] if i<len(n["witnesses"]) else None)
        actors.append({
            "id":ACTOR_PREFIX+str(i), "index":i,"position":datum["cell"],
            "home":datum["cell"],"work":q["sites"][i]["cell"],
            "role":datum["role"],
            "authored_dialogue_role":alias["id"] if alias else None,
            "authored_citizen_role":citizen["id"] if citizen else None,
            "topic":alias["topic"] if alias else None,
            "authored_name":alias["name"] if alias else "Original Citizen "+str(i),
            "trust":config["dialogue"]["starting_trust"],
            "patience":alias["initial_patience"] if alias else
                       config["dialogue"]["speaker_patience"],
            "bond":0,"supported":0,"heard_firsthand":[],
            "witness_memories":[],"dialogue_memories":[],
            "last_spoke":None,"conversations":0,
            "suspicion":0,
            "schedule_phase":"home","movement_steps":0,
        })
    return {
        "tick":0, "player":q["player_spawn"],"map_side":SIDE,
        "obstacles":list(q["obstacles"]),
        "sites":[{**site,"aid_received":0} for site in q["sites"]],
        "actors":actors,
        "resources":{
            "supplies":config["quest_director"]["starting_supplies"],
            "stamina":config["quest_director"]["stamina"],
            "influence":config["dialogue"]["starting_influence"],
            "gold":config["quest_director"]["starting_gold"],
            "reputation":config["quest_director"]["starting_reputation"],
        },
        "events_ledger":[],"quests":[],"dialogues":[],"choices":[],
        "councils":[],"resolved_count":0,
        "last_event_id":-1,"last_quest_id":-1,
        "retired":False,"finished":False,"failed":False,
        "events":[],"calendar":"shared_authoritative_world_clock",
        "provenance":"authored_game_original_single_actor_world",
    }


def _actor(state,index):
    if type(index) is not int or index<0 or index>=len(state["actors"]):
        raise UnifiedWorldError("actor not embodied in the original shared world")
    return state["actors"][index]


def _site(state,index):
    if type(index) is not int or not 0<=index<len(state["sites"]):
        raise UnifiedWorldError("unregistered world site")
    return state["sites"][index]


def _require_near(player,other):
    if _distance(player,other)>1:
        raise UnifiedWorldError("physical participant outside local contact range")


def _charge(state,kind,cost):
    if cost<0 or state["resources"][kind]<cost:
        raise UnifiedWorldError("finite unified world "+kind+" payment unavailable")
    state["resources"][kind]-=cost


def _remember(actor,event,limit):
    memories=actor["witness_memories"]
    memories.append({
        "event_id":event["id"],"source":"physical_line_of_sight",
        "observed_at":event["tick"],"kind":event["kind"],
        "site_id":event["site_id"],
    })
    actor["witness_memories"]=memories[-limit:]


def _event(state,config,kind,site,occurrences):
    if len(state["events_ledger"])>=min(96,config["quest_director"]["event_budget"]):
        raise UnifiedWorldError("authoritative event log has reached fixed budget")
    sight_radius=min(6,config["quest_director"]["witness_radius"])
    blockers=set(state["obstacles"])
    observers=[
        actor["index"] for actor in state["actors"]
        if _distance(actor["position"],site["cell"])<=min(
            sight_radius,config["quest_director"]["npc_perception"])
        and _sight(actor["position"],site["cell"],blockers)
    ]
    eid=state["last_event_id"]+1
    receipt={
        "id":eid,"tick":state["tick"],"kind":kind,
        "site_id":site["id"],"cell":site["cell"],
        "actor":"player","direct_witnesses":observers,
        "original_source":"physical_same_world_player_action",
    }
    state["events_ledger"].append(receipt)
    state["last_event_id"]=eid
    for i in observers:
        _remember(state["actors"][i],receipt,config["quest_director"]["memory_records"])
    occurrences.append("canonical_physical_event_committed")
    if observers and len(state["quests"])<min(12,config["quest_director"]["active_quests"]):
        qid=state["last_quest_id"]+1
        quest={
            "id":qid,"site_id":site["id"],"source_event":eid,
            "trigger":kind,"direct_witnesses":observers,
            "testimonies":[],"pledges":[],"followups":0,
            "choice":None,"status":"active","ending":None,
            "created_tick":state["tick"],"resolved_at":None,
        }
        state["quests"].append(quest)
        state["last_quest_id"]=qid
        occurrences.append("living_citizens_created_witnessed_causal_quest")
    else:
        occurrences.append("event_remained_unverified_without_witnesses")
    return receipt


def _quest_from_memory(state,actor):
    for memory in reversed(actor["witness_memories"]):
        for quest in state["quests"]:
            if quest["source_event"]==memory["event_id"] and (
                quest["status"]=="active"
            ):
                return quest
    return None


def _simulate_action(state,config,action):
    if action not in ACTIONS:
        raise UnifiedWorldError("unregistered unified NPC action")
    if state["finished"] or state["failed"]:
        raise UnifiedWorldError("unified world has already ended")
    if state["tick"]>=min(96,config["npc_society"]["turn_limit"]):
        raise UnifiedWorldError("original shared-world finite turn budget exhausted")
    occurrences=[];before=state["player"]
    d=config["dialogue"];q=config["quest_director"]
    if action.startswith("move:"):
        heading=action[5:];new=before+MOVES[heading]
        if new not in _neighbors(before) or new in state["obstacles"]:
            raise UnifiedWorldError("player move is not a valid physical adjacent tile")
        _charge(state,"stamina",q["movement_stamina"])
        state["player"]=new
        occurrences.append("player_advanced_one_authoritative_world_tile")
    elif action=="rest":
        state["resources"]["stamina"]=min(
            q["stamina"],state["resources"]["stamina"]+q["rest_stamina"])
        occurrences.append("bounded_shared_world_stamina_recovery")
    elif action in ("inspect","wait"):
        occurrences.append("shared_world_observation_without_fake_progress")
    elif action=="retire":
        if state["resolved_count"]<1:
            raise UnifiedWorldError("optional final chapter requires authentic quest resolution")
        state["retired"]=state["finished"]=True
        occurrences.append("optional_verified_original_epilogue")
    else:
        verb,index=action.split(":");i=int(index)
        if verb in ("speak","support","observe"):
            actor=_actor(state,i)
            _require_near(state["player"],actor["position"])
            if verb=="observe":
                occurrences.append("live_original_npc_observed_at_actual_location")
            elif verb=="speak":
                if actor["patience"]<=0 or (
                    sum(a["conversations"] for a in state["actors"])>=d["lines_per_scene"]
                ):
                    raise UnifiedWorldError("bounded speaker patience or text line budget spent")
                quest=_quest_from_memory(state,actor)
                if quest and i in quest["testimonies"]:
                    quest=None
                actor["patience"]-=1
                actor["conversations"]+=1
                actor["last_spoke"]=state["tick"]
                statement={
                    "actor":actor["id"],"speaker_index":i,
                    "time":state["tick"],"source":(
                        "direct_original_world_eyewitness" if quest else
                        "ordinary_original_firsthand_conversation"
                    ),
                    "event_id":quest["source_event"] if quest else None,
                    "quest_id":quest["id"] if quest else None,
                    "subject":actor["topic"],
                }
                if quest:
                    quest["testimonies"].append(i)
                    actor["heard_firsthand"].append(quest["source_event"])
                state["dialogues"].append(statement)
                actor["dialogue_memories"].append({
                    "tick":state["tick"],"source":statement["source"],
                    "quest_id":statement["quest_id"],
                })
                occurrences.append("source_npc_speaks_from_one_real_physical_body")
            else:
                if not d["choice_consequences"] or not actor["conversations"]:
                    raise UnifiedWorldError("material social support requires actual prior speech")
                if actor["patience"]<1:
                    raise UnifiedWorldError("social participant refuses exhausted conversation")
                _charge(state,"influence",d["support_cost"])
                _charge(state,"supplies",q["help_supplies"])
                actor["patience"]-=1
                actor["trust"]=min(d["trust_cap"],actor["trust"]+d["support_trust_gain"])
                actor["bond"]+=config["npc_society"]["help_bond"]
                actor["supported"]+=1
                state["resources"]["reputation"]+=d["support_reputation"]
                quest=_quest_from_memory(state,actor)
                if not quest or i not in quest["testimonies"]:
                    raise UnifiedWorldError("paid support cannot create unwitnessed quest evidence")
                if quest["choice"] is not None and quest["choice"]!="support":
                    raise UnifiedWorldError("cannot rewrite an existing causal branch")
                quest["choice"]="support"
                quest["pledges"].append(i)
                state["choices"].append({
                    "actor":actor["id"],"quest_id":quest["id"],
                    "influence_paid":d["support_cost"],
                    "supplies_paid":q["help_supplies"],
                    "tick":state["tick"],"branch":"support",
                })
                occurrences.append("single_world_social_choice_paid_and_committed")
        elif verb in ("discover","help","harm","followup","resolve","council"):
            site=_site(state,i)
            _require_near(state["player"],site["cell"])
            if verb in ("discover","help","harm"):
                _charge(state,"stamina",q["action_stamina"])
                if verb=="discover":
                    if site["stock"]<q["gather_units"]:
                        raise UnifiedWorldError("finite original archaeological site stock exhausted")
                    site["stock"]-=q["gather_units"]
                    state["resources"]["supplies"]+=q["gather_units"]
                    _event(state,config,"discover",site,occurrences)
                elif verb=="help":
                    _charge(state,"supplies",q["help_supplies"])
                    site["aid_received"]+=q["help_supplies"]
                    site["integrity"]=min(q["site_integrity"],
                                         site["integrity"]+q["help_power"])
                    _event(state,config,"help",site,occurrences)
                else:
                    if site["integrity"]<1:
                        raise UnifiedWorldError("already collapsed original civic site cannot be harmed")
                    site["integrity"]=max(0,site["integrity"]-q["harm_power"])
                    _event(state,config,"harm",site,occurrences)
            elif verb=="followup":
                quest=next((a for a in state["quests"] if a["site_id"]==i and
                            a["status"]=="active" and a["choice"]=="support"),None)
                if quest is None or not quest["testimonies"] or not quest["pledges"]:
                    raise UnifiedWorldError("material quest followup requires real testimony and pledge")
                _charge(state,"stamina",q["action_stamina"])
                _charge(state,"supplies",q["help_supplies"])
                site["aid_received"]+=q["help_supplies"]
                quest["followups"]+=1
                occurrences.append("real_paid_followup_advanced_verified_quest")
            elif verb=="resolve":
                quest=next((a for a in state["quests"] if a["site_id"]==i and
                            a["status"]=="active" and a["choice"]=="support"
                            and a["pledges"] and a["testimonies"]),None)
                if quest is None or quest["followups"]<q["consequence_depth"]:
                    raise UnifiedWorldError("unified quest needs all finite material obligations")
                quest["status"]="resolved";quest["ending"]="restored"
                quest["resolved_at"]=state["tick"]
                state["resolved_count"]+=1
                state["resources"]["gold"]+=q["reward_gold"]
                state["resources"]["reputation"]+=q["reputation_gain"]
                occurrences.append("canonical_quest_resolved_from_paid_real_actions")
            else:
                quest=next((a for a in state["quests"] if a["site_id"]==i and
                            a["status"]=="resolved"),None)
                if quest is None or i in state["councils"]:
                    raise UnifiedWorldError("unique social council requires resolved original site")
                if len(set(quest["testimonies"]))<2:
                    raise UnifiedWorldError("council cannot forge two independent direct witnesses")
                if not any(c["quest_id"]==quest["id"] for c in state["choices"]):
                    raise UnifiedWorldError("council has no actual paid civic trust")
                state["councils"].append(i)
                occurrences.append("distinct_same_world_direct_eyewitnesses_held_public_council")
        else:
            raise UnifiedWorldError("unrecognized original shared-world effect")
    state["tick"]+=1
    return occurrences


def _schedule(state,config):
    """One clock and one positional record per citizen; movement after actions."""
    blocked=set(state["obstacles"])
    occupied=set(a["position"] for a in state["actors"])
    moves=[];tick=state["tick"]
    period=config["npc_society"]["day_length"]
    working=(tick%period)<period//2
    for actor in state["actors"]:
        before=actor["position"]
        goal=actor["work"] if working else actor["home"]
        occupied.remove(before)
        following=_step_toward(before,goal,blocked,occupied)
        actor["position"]=following
        actor["schedule_phase"]="work" if working else "home"
        if before!=following:
            actor["movement_steps"]+=1
            moves.append({
                "actor":actor["id"],"from":before,"to":following,
                "tick":tick,"path":"one_real_tile",
            })
        occupied.add(following)
        lifetime=config["dialogue"]["memory_turns"]
        if lifetime<=0:
            actor["dialogue_memories"]=[]
        else:
            actor["dialogue_memories"]=[
                x for x in actor["dialogue_memories"]
                if tick-x["tick"]<lifetime
            ][-32:]
        # Witness memory is independent of subjective dialogue memory: an
        # observed historical event remains immutable on the event ledger,
        # even when the witness's bounded working memory is overwritten.
    if len({a["position"] for a in state["actors"]})!=len(state["actors"]):
        raise UnifiedWorldError("shared NPC positional authority attempted body collision")
    return moves


def run_unified_npc_world(actions=(),settings=None,*,scenes=None,seed=0):
    if type(actions) not in (list,tuple) or len(actions)>MAX_COMMANDS:
        raise UnifiedWorldError("at most 96 real original-world commands allowed")
    config,worlds,identities=_sources(settings,scenes,seed)
    state=_initial(config,worlds)
    frames=[];previous=_hash({
        "schema":SCHEMA,"seed":seed,"source_ids":identities,
        "action_budget":MAX_COMMANDS,
    })
    for number,action in enumerate(actions):
        if type(action) is not str or action not in ACTIONS:
            raise UnifiedWorldError("unregistered or invalid original unified world command")
        # Each request executes on an independently reconstructible authority,
        # not by editing a client-provided actor/quest/achievement.
        before=_hash(state)
        occurrences=_simulate_action(state,config,action)
        scheduled=_schedule(state,config)
        state["events"]=list(occurrences)+(
            ["actual_authoritative_resident_schedule_advanced"] if scheduled else []
        )
        step={
            "index":number,"action":action,"tick":state["tick"],
            "before":before,"source_events":occurrences,
            "npc_moves":scheduled,
            "after":_hash(state),
            "ordered_phases":list(ORDER),"previous":previous,
        }
        step["digest"]=_hash(step)
        previous=step["digest"];frames.append(step)
    record={
        "schema":SCHEMA,"seed":seed,"sources":worlds,
        "settings":config,"source_identities":identities,
        "actions":list(actions),"state":state,"event_frames":frames,
        "head_digest":previous,
        "canonical_physical_actor_count":len(state["actors"]),
        "independently_replayable":True,
        "legacy_engines_simultaneously_executed":False,
        "native_unified_engine_executed":False,
        "model_weights_promoted":False,
        "source_files_mutated":False,
        "publication_certified":False,
    }
    return {**record,"digest":_hash(record)}


def verify_unified_npc_world(receipt):
    if type(receipt) is not dict or receipt.get("schema")!=SCHEMA:
        raise UnifiedWorldError("signed-schema original world receipt required")
    try:
        if len(_serialized(receipt).encode("utf-8"))>MAX_BYTES:
            raise UnifiedWorldError("oversized shared world denied")
        expected=run_unified_npc_world(
            receipt["actions"],receipt["settings"],
            scenes=receipt["sources"],seed=receipt["seed"],
        )
    except (KeyError,IndexError,TypeError) as exc:
        raise UnifiedWorldError("malformed original unified world replay record") from exc
    if expected!=receipt:
        raise UnifiedWorldError("canonical actor, clock, quest or eyewitness history was forged")
    return True


__all__=[
    "SCHEMA","SIDE","ACTIONS","ORDER","ACTOR_PREFIX",
    "UnifiedWorldError","run_unified_npc_world","verify_unified_npc_world",
]
