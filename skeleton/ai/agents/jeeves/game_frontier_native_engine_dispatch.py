"""Source-verified local Godot quest dispatcher: verified actions, not AI scripts.

An explicitly approved native quest checkpoint is cold replayed from the
signed GDD, exact actor/source catalog and immutable Godot physics journal.
The resulting fixed-schema dispatch bundle is DATA, not executable GDScript.
Its approval is a local operator selection; the digest is integrity, not a
signature or network attestation. World canon remains unchanged.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

from .game_frontier_native_quest_session import (
    NativeQuestSessionError,_sha,parse_native_quest_graph,authored_page_digest,
)
from .game_frontier_native_quest_audit import audit_native_quest_checkpoint
from .game_frontier_native_session_checkpoint import advance_native_quest_window


_CAMERA_MODES={"authored":0,"follow":1,"orbit":2,"overhead":3}
_INSTRUMENT_FOCUS=frozenset(("flight","landing","camera"))
_LOCAL_HEALTH_CAP=100
_LOCAL_XP_CAP=9900


def _health_amount(value: object) -> int:
    if (type(value) is not str or not 1<=len(value)<=3
        or any(ch not in "0123456789" for ch in value)
        or (len(value)>1 and value[0]=="0")
        or not 1<=int(value)<=_LOCAL_HEALTH_CAP):
        raise NativeQuestSessionError("local health delta requires canonical 1..100")
    return int(value)


def _local_item_id(value: object) -> str:
    if (type(value) is not str or not 1<=len(value)<=128
        or not value[0].isascii() or not value[0].isalpha()
        or any(not(c.isascii() and (c.isalnum() or c in "_.-")) for c in value)):
        raise NativeQuestSessionError("invalid local inventory item identifier")
    return value




_ALLOWED=frozenset((
    "start_quest","advance_quest","set_flag","show_dialogue",
    "play_cutscene","play_music","spatial_audio","change_camera",
    "inspect_instrument","trigger_impact_fx","trigger_foliage_fx",
    "craft_item","set_npc_emotion",
    "take_damage","heal_health","consume_item","award_xp",
    "unlock_skill","set_faction_reputation",
))


def compile_native_godot_dispatch(
    journal,pages,quest_graph,approvals,checkpoint, *, actor_id: str,
    scene_candidate_digest: str, max_frames: int = 4096,
    frames_per_window: int = 256,
) -> dict:
    """Cold-audit a checkpoint; materialize only verified approved actions.

    The payload can be installed by an operator into an existing Godot
    scene; Godot validates the file digest against its source scene and
    applies the actions in order with an on-disk game-state receipt.
    """
    if (type(max_frames) is not int or not 1<=max_frames<=4096 or
        type(frames_per_window) is not int or not 1<=frames_per_window<=4096):
        raise NativeQuestSessionError("bounded Godot dispatch export required")
    proof=audit_native_quest_checkpoint(
        journal,pages,quest_graph,approvals,checkpoint,
        actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
    last=checkpoint["frame"]
    if last+1>max_frames:
        raise NativeQuestSessionError(
            "interactive dispatch snapshot exceeds explicit frame limit")
    catalog=parse_native_quest_graph(quest_graph)
    commands=[]
    inventory={}
    npc_moods={}
    selected_camera=0
    instrument_focus="none"
    local_health=_LOCAL_HEALTH_CAP
    local_xp=0
    progression_events=[]
    unlocked_skills={}
    factions={}
    faction_events=[]
    local_effect_history=[]
    signed_actors={a["id"] for a in journal.native_sample(0)["actors"]}
    cursor=None
    for first in range(0,last+1,frames_per_window):
        stop=min(last,first+frames_per_window-1)
        response=advance_native_quest_window(
            journal,pages,quest_graph,approvals,
            actor_id=actor_id,scene_candidate_digest=scene_candidate_digest,
            through_frame=stop,previous_checkpoint=cursor,
            expected_checkpoint_digest=(
                cursor["receipt_digest"] if cursor is not None else None),
            max_frames=frames_per_window)
        for entry in response["entries"]:
            for approved in entry["approved_pages"]:
                for index,action in enumerate(approved["actions"]):
                    if action["kind"] not in _ALLOWED:
                        raise NativeQuestSessionError(
                            "Godot dispatcher refuses unimplemented world mutations")
                    if action["kind"]=="inspect_instrument":
                        if action["value"] not in _INSTRUMENT_FOCUS:
                            raise NativeQuestSessionError("unknown approved flight instrument")
                        instrument_focus=action["value"]
                    if action["kind"]=="change_camera":
                        if action["value"] not in _CAMERA_MODES:
                            raise NativeQuestSessionError("unauthorized Godot camera preset")
                        selected_camera=_CAMERA_MODES[action["value"]]
                    if action["kind"]=="set_faction_reputation":
                        parts=action["value"].split(":")
                        if len(parts)!=2 or len(parts[1])<2 or parts[1][0] not in "+-":
                            raise NativeQuestSessionError("faction adjustment requires id:+N or id:-N")
                        faction=_local_item_id(parts[0])
                        amount=_health_amount(parts[1][1:])
                        if faction not in factions and len(factions)>=128:
                            raise NativeQuestSessionError("faction standing budget exceeded")
                        delta=amount if parts[1][0]=="+" else -amount
                        factions[faction]=max(-100,min(100,factions.get(faction,0)+delta))
                        faction_events.append({
                            "frame":entry["frame"],"page_id":approved["page_id"],
                            "faction":faction,"value":action["value"],
                            "resulting_reputation":factions[faction],
                            "source_frame_digest":entry["source_frame_receipt_digest"],
                        })
                    if action["kind"]=="unlock_skill":
                        token=action["value"].split(":")
                        if len(token)!=2:
                            raise NativeQuestSessionError("skill unlock requires skill:level")
                        name=_local_item_id(token[0])
                        threshold=_health_amount(token[1])
                        if (name in unlocked_skills or len(unlocked_skills)>=128
                            or 1+local_xp//100<threshold):
                            raise NativeQuestSessionError("skill level prerequisite or duplicate rejected")
                        unlocked_skills[name]=threshold
                        progression_events.append({
                            "frame":entry["frame"],"page_id":approved["page_id"],
                            "kind":"unlock_skill","value":action["value"],
                            "resulting_xp":local_xp,
                            "resulting_level":1+local_xp//100,
                            "source_frame_digest":entry["source_frame_receipt_digest"],
                        })
                    if action["kind"]=="award_xp":
                        amount=_health_amount(action["value"])
                        if local_xp+amount>_LOCAL_XP_CAP:
                            raise NativeQuestSessionError("experience level cap exceeded")
                        local_xp+=amount
                        progression_events.append({
                            "frame":entry["frame"],"page_id":approved["page_id"],
                            "kind":"award_xp","value":action["value"],
                            "resulting_xp":local_xp,
                            "resulting_level":1+local_xp//100,
                            "source_frame_digest":entry["source_frame_receipt_digest"],
                        })
                    if action["kind"] in ("take_damage","heal_health"):
                        delta=_health_amount(action["value"])
                        local_health=(max(0,local_health-delta)
                            if action["kind"]=="take_damage"
                            else min(_LOCAL_HEALTH_CAP,local_health+delta))
                        local_effect_history.append({
                            "frame":entry["frame"],"page_id":approved["page_id"],
                            "kind":action["kind"],"value":action["value"],
                            "resulting_health":local_health,
                            "source_frame_digest":entry["source_frame_receipt_digest"],
                        })
                    if action["kind"]=="consume_item":
                        item=_local_item_id(action["value"])
                        if inventory.get(item,0)<1:
                            raise NativeQuestSessionError("cannot consume absent approved item")
                        inventory[item]-=1
                        if inventory[item]==0:
                            del inventory[item]
                        local_effect_history.append({
                            "frame":entry["frame"],"page_id":approved["page_id"],
                            "kind":action["kind"],"value":item,
                            "resulting_health":local_health,
                            "source_frame_digest":entry["source_frame_receipt_digest"],
                        })
                    if action["kind"]=="craft_item":
                        item=_local_item_id(action["value"])
                        if (inventory.get(item,0)>=9999 or
                            (item not in inventory and len(inventory)>=1024)):
                            raise NativeQuestSessionError("invalid local crafted item or inventory limit")
                        inventory[item]=inventory.get(item,0)+1
                    if action["kind"]=="set_npc_emotion":
                        parts=action["value"].split(":")
                        if (len(parts)!=2 or parts[0] not in signed_actors or
                            parts[0]==actor_id or parts[1] not in
                            ("calm","alert","friendly","afraid","hostile","curious")):
                            raise NativeQuestSessionError("NPC emotion must target signed game actor")
                        npc_moods[parts[0]]=parts[1]
                    commands.append({
                        "frame":entry["frame"],
                        "page_id":approved["page_id"],
                        "action_index":index,
                        "kind":action["kind"],
                        "target":action["target"],
                        "value":action["value"],
                        "channel":action["channel"],
                        "native_frame_receipt_digest":entry["source_frame_receipt_digest"],
                        "approved_event_evidence_digest":approved["event_evidence_digest"],
                    })
        cursor=response["checkpoint"]
    if cursor!=checkpoint or len(commands)>65536:
        raise NativeQuestSessionError("dispatch actions differ from audited source prefix")
    quest_history=[]
    for command in commands:
        if command["kind"] not in ("start_quest","advance_quest"):
            continue
        token=command["value"].split(":")
        quest_id=token[0]
        authored=next((q for q in catalog["quests"] if q["id"]==quest_id),None)
        if authored is None:
            raise NativeQuestSessionError("quest history refers to unknown author")
        stage_id=authored["start"] if command["kind"]=="start_quest" else token[1]
        stage=next((s for s in authored["stages"] if s["id"]==stage_id),None)
        if stage is None:
            raise NativeQuestSessionError("history points at unapproved quest objective")
        quest_history.append({
            "frame":command["frame"],"page_id":command["page_id"],
            "quest_id":quest_id,"title":authored["title"],
            "stage_id":stage_id,"objective":stage["objective"],
            "completed":len(stage["next"])==0,
            "source_frame_digest":command["native_frame_receipt_digest"],
        })
    result={
        "schema":"skeleton.game.native_godot_dispatch.v1",
        "source":"operator_approved_native_quest_source_replay",
        "authority":"local_gameplay_state_only_not_canonical_GDD_or_network_attestation",
        "actor_id":actor_id,
        "track":journal.track,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "authored_pages_digest":authored_page_digest(pages),
        "quest_graph_digest":catalog["receipt_digest"],
        "approved_manifest_digest":approvals["receipt_digest"],
        "verified_checkpoint_digest":checkpoint["receipt_digest"],
        "independent_cold_audit_digest":proof["receipt_digest"],
        "source_through_frame":last,
        "available_branch_options":{q["id"]:[
            {"stage_id":next_id,
             "objective":next(stage["objective"] for stage in q["stages"]
                              if stage["id"]==next_id)}
            for stage in q["stages"] if stage["id"]==
                checkpoint["quests"].get(q["id"],{}).get("stage")
            for next_id in stage["next"]]
            for q in catalog["quests"] if q["id"] in checkpoint["quests"]},
        "quest_objectives":{item["id"]:{
            stage["id"]:stage["objective"] for stage in item["stages"]}
            for item in catalog["quests"]},
        "quest_titles":{item["id"]:item["title"] for item in catalog["quests"]},
        "quest_start_stages":{item["id"]:item["start"]
                              for item in catalog["quests"]},
        "quest_edges":{item["id"]:{
            stage["id"]:stage["next"] for stage in item["stages"]}
            for item in catalog["quests"]},
        "initial_flags":dict(approvals["initial_flags"]),
        "expected_flags":checkpoint["flags"],
        "expected_inventory":inventory,
        "expected_local_health":local_health,
        "expected_local_xp":local_xp,
        "expected_local_level":1+local_xp//100,
        "expected_progression_events":progression_events,
        "expected_unlocked_skills":unlocked_skills,
        "expected_faction_reputation":factions,
        "expected_faction_events":faction_events,
        "expected_local_effect_history":local_effect_history,
        "expected_camera_mode":selected_camera,
        "expected_instrument_focus":instrument_focus,
        "expected_npc_emotions":npc_moods,
        "expected_quests":checkpoint["quests"],
        "actions":commands,
        "expected_quest_history":quest_history,
        "expected_action_trace":[{
            "frame":c["frame"],"page_id":c["page_id"],
            "action_index":c["action_index"],"kind":c["kind"],
            "native_frame_receipt_digest":c["native_frame_receipt_digest"],
            "approved_event_evidence_digest":c["approved_event_evidence_digest"],
        } for c in commands],
    }
    result["receipt_digest"]=_sha(result)
    return result


def verify_native_godot_dispatch(
    journal,pages,quest_graph,approvals,checkpoint,recorded: object,**kwargs
) -> bool:
    rebuilt=compile_native_godot_dispatch(
        journal,pages,quest_graph,approvals,checkpoint,**kwargs)
    if type(recorded) is not dict or recorded!=rebuilt:
        raise NativeQuestSessionError("in-engine dispatch bundle differs from verified journal")
    return True


def canonical_dispatch_json(dispatch: dict) -> str:
    """Exact byte stream for Godot FileAccess.get_sha256() comparison."""
    if (type(dispatch) is not dict or
        dispatch.get("schema")!="skeleton.game.native_godot_dispatch.v1"
        or dispatch.get("receipt_digest")!=_sha({
            k:v for k,v in dispatch.items() if k!="receipt_digest"})):
        raise NativeQuestSessionError("unverified dispatch bundle JSON")
    return json.dumps(dispatch,sort_keys=True,separators=(",",":"),
                      allow_nan=False)+"\n"


def dispatch_file_sha256(dispatch: dict) -> str:
    return sha256(canonical_dispatch_json(dispatch).encode("utf-8")).hexdigest()
