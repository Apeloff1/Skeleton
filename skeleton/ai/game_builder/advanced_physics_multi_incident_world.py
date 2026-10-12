"""Source-bound multi-incident NPC world campaign.

A single independently replayed original game/physics session can contain up
to eight distinct physical objects. Every observed contact is attributed by
the canonical fixture index and independently reconstructed; multiple hits to
one object create one bounded incident, while different contacted objects can
trigger distinct local eyewitness quests. No guessed fixture, remote testimony,
client-authored health, or source file mutations.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_physics_interop import rehearse_physics_encounter, verify_physics_encounter
from .advanced_gameplay_runtime import verify_advanced_session
from .advanced_level_scenes import validate_advanced_scene
from .advanced_quest_director_runtime import (
    start as quest_start, apply_scene as quest_apply,
    step as quest_step, apply_verified_external_physical_incident,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.physics_multi_incident_npc.v1"
MAX_OBJECTS=8
MAX_FOLLOWUPS=24

class MultiIncidentError(ValueError):
    """An original physical-NPC event failed verified source custody."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _bindings(bindings):
    if type(bindings) not in (tuple,list) or not 1<=len(bindings)<=MAX_OBJECTS:
        raise MultiIncidentError("one to eight source-to-site incident mappings required")
    sources=set()
    sites=set()
    verified=[]
    for item in bindings:
        if (type(item) is not dict or set(item)!={"source_id","site_id"} or
            type(item["source_id"]) is not int or not 0<=item["source_id"]<=1000000 or
            type(item["site_id"]) is not int or not 0<=item["site_id"]<4):
            raise MultiIncidentError("mapping requires exact nonnegative source ID and site")
        if item["source_id"] in sources or item["site_id"] in sites:
            raise MultiIncidentError("one-to-one source identity and quest site binding required")
        sources.add(item["source_id"])
        sites.add(item["site_id"])
        verified.append(dict(item))
    return verified


def run_multi_incident_world(source_session,quest_scene,
                             source_settings=None,quest_settings=None, *,
                             physics_actions=("push:east",)*8,bindings=None,
                             world_actions=()):
    approved=_bindings(bindings)
    if (type(world_actions) not in (tuple,list) or
        len(world_actions)>MAX_FOLLOWUPS or
        any(type(a) is not str for a in world_actions)):
        raise MultiIncidentError("finite original world followup transcript required")
    try:
        source_cfg=make_editor_document(source_session["editor"],source_settings)["settings"]
        npc_cfg=make_editor_document("quest_director",quest_settings)["settings"]
        verify_advanced_session(source_session,source_cfg)
        if source_session.get("scene") is None:
            raise MultiIncidentError("signed original source game scene is required")
        source=validate_advanced_scene(source_session["scene"],source_cfg)
        world_source=validate_advanced_scene(quest_scene,npc_cfg)
        encounter=rehearse_physics_encounter(source_session,source_cfg,physics_actions)
        verify_physics_encounter(encounter,source_session,source_cfg)
        witnesses=encounter["witnesses"]
        known={w["source_id"]:i for i,w in enumerate(witnesses)}
        if len(known)!=len(witnesses) or any(b["source_id"] not in known for b in approved):
            raise MultiIncidentError("source object not uniquely present in approved original game")
        state=encounter["physics_session"]["state"]
        history=state["fixture_contact_events"]
        counts=state["fixture_contact_counts"]
        # Bounded recent contact list is not a full historical ledger after
        # eviction. Do not fabricate chronology from aggregate counts alone.
        if sum(counts)!=len(history):
            raise MultiIncidentError("bounded collision history cannot prove all incident times")
        tally=[0]*len(witnesses)
        earliest={}
        for event in history:
            idx=event["fixture_index"]
            if type(idx) is not int or not 0<=idx<len(witnesses):
                raise MultiIncidentError("physical collision fixture identity is invalid")
            tally[idx]+=1
            earliest.setdefault(idx,(event["tick"],event["frame"]))
        if tally!=counts:
            raise MultiIncidentError("physical fixture counts disagree with ordered incident history")
        world=quest_start(npc_cfg,world_source["seed"])
        quest_apply(world,npc_cfg,world_source["layout"])
        incidents=[]
        entries=[]
        bound={b["source_id"]:b for b in approved}
        # True physics chronology; source order provides deterministic ties.
        ordered=sorted(
            ((earliest[i],i,w) for i,w in enumerate(witnesses)
             if counts[i] and w["source_id"] in bound),
            key=lambda item:(item[0][0],item[0][1],item[1]))
        for first,index,object_ref in ordered:
            identity=object_ref["source_id"]
            binding=bound[identity]
            severity=min(3,counts[index])
            receipt={
                "interop_digest":encounter["digest"],
                "source_editor":encounter["source_editor"],
                "source_id":identity,
            }
            incident=apply_verified_external_physical_incident(
                world,npc_cfg,binding["site_id"],receipt,impact_severity=severity)
            quests=[q["id"] for q in world["quests"] if q["origin_event"]==incident["id"]]
            entries.append({
                "source_id":identity,"source_type":object_ref["source_type"],
                "fixture_index":index,"site_id":binding["site_id"],
                "physics_first_tick":first[0],"physics_first_frame":first[1],
                "real_contact_count":counts[index],"severity":severity,
                "incident":incident,"direct_witnesses":list(incident["direct_witnesses"]),
                "quest_ids":quests,"world_turn":world["turn"],
            })
            incidents.append(incident)
        timeline=[]
        for action in world_actions:
            quest_step(world,npc_cfg,action)
            timeline.append({
                "action":action,"turn":world["turn"],"tick":world["tick"],
                "events":list(world["events"]),
                "quests_completed":world["quests_completed"],
                "quests_exploited":world["quests_exploited"],
            })
        record={
            "schema":SCHEMA,"source_editor":source_session["editor"],
            "source_session_digest":source_session["digest"],
            "source_scene_digest":source["digest"],
            "quest_scene_digest":world_source["digest"],
            "interop_digest":encounter["digest"],
            "physics_session_digest":encounter["physics_session"]["digest"],
            "physics_actions":list(physics_actions),
            "bindings":approved,"world_actions":list(world_actions),
            "observed_fixture_impacts":encounter["observed_fixture_impacts"],
            "source_fixture_impacts":encounter["source_fixture_impacts"],
            "incidents":entries,"world_timeline":timeline,
            "world_state":world,"source_game_unchanged":True,
            "native_hardware_verified":False,"automatic_promotion_approved":False,
        }
    except MultiIncidentError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise MultiIncidentError(
            "original game, physical source or NPC testimony failed independent verification"
        ) from exc
    return {**record,"digest":_digest(record)}


def verify_multi_incident_world(proof,source_session,quest_scene,
                                source_settings=None,quest_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise MultiIncidentError("signed multiple-incident world proof required")
    try:
        replay=run_multi_incident_world(
            source_session,quest_scene,source_settings,quest_settings,
            physics_actions=proof["physics_actions"],bindings=proof["bindings"],
            world_actions=proof["world_actions"])
    except (KeyError,TypeError,IndexError) as exc:
        raise MultiIncidentError("multi-incident proof lacks original action source") from exc
    if replay!=proof:
        raise MultiIncidentError("source collision order, witnesses, quests or reward was forged")
    return True


__all__=["SCHEMA","MAX_OBJECTS","MAX_FOLLOWUPS","MultiIncidentError",
         "run_multi_incident_world","verify_multi_incident_world"]
