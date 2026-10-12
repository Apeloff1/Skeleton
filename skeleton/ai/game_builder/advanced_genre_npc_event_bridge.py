"""Source-traceable original farming, sailing and flight NPC world incidents.

Only audited genre actions that really executed their earned event may cross
into a persistent NPC world. A client-requested editor label, image, claim or
invented achievement cannot mint world cargo, eyewitnesses or a quest.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import verify_advanced_session
from .advanced_level_scenes import validate_advanced_scene
from .advanced_quest_director_runtime import (
    start as quest_start,apply_scene as quest_apply,
    step as quest_step,apply_verified_external_gameplay_event,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.cross_genre_npc_events.v1"
MAX_EVENTS=8
MAX_WORLD_ACTIONS=24
SUPPORTED={
    "farming":("mature_crop_harvested","discover"),
    "sailing":("original_cargo_delivered","help"),
    "flight":("runway_landing_confirmed","discover"),
}

class CrossGenreWorldError(ValueError):
    """An original genre event source, NPC consequence or replay was invalid."""


def _sha(data):
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _qualifies(source,frame):
    name=source["editor"]
    trigger,kind=SUPPORTED[name]
    if trigger not in frame["events"]:
        return None
    action=frame["action"]
    if name=="farming":
        if not action.startswith("harvest:") or source["state"]["harvested"]<=0:
            return None
    elif name=="sailing":
        if action!="dock" or source["state"]["cargo_delivered"]<=0:
            return None
    else:
        if action!="land" or source["state"]["landed"] is not True:
            return None
    return trigger,kind


def run_cross_genre_world(source,world_scene,bindings,source_settings=None,
                          world_settings=None,*,world_actions=()):
    if type(source) is not dict or source.get("editor") not in SUPPORTED:
        raise CrossGenreWorldError("only reviewed earned farming, sailing and flight events qualify")
    if (type(bindings) not in (list,tuple) or not 1<=len(bindings)<=MAX_EVENTS or
        type(world_actions) not in (list,tuple) or
        len(world_actions)>MAX_WORLD_ACTIONS or
        any(type(action) is not str for action in world_actions)):
        raise CrossGenreWorldError("finite original event/site mappings and world actions required")
    try:
        source_cfg=make_editor_document(source["editor"],source_settings)["settings"]
        world_cfg=make_editor_document("quest_director",world_settings)["settings"]
        verify_advanced_session(source,source_cfg)
        if source["scene"] is None:
            raise CrossGenreWorldError("authored source scene required for original genre events")
        scene=validate_advanced_scene(source["scene"],source_cfg)
        world=validate_advanced_scene(world_scene,world_cfg)
        real_events=[]
        approved=set()
        for binding in bindings:
            if (type(binding) is not dict or
                set(binding)!={"trace_index","site_id"} or
                type(binding["trace_index"]) is not int or
                type(binding["site_id"]) is not int or
                not 0<=binding["trace_index"]<len(source["trace"]) or
                not 0<=binding["site_id"]<4 or
                binding["trace_index"] in approved):
                raise CrossGenreWorldError("exact unique original source action index required")
            approved.add(binding["trace_index"])
            frame=source["trace"][binding["trace_index"]]
            event=_qualifies(source,frame)
            if event is None:
                raise CrossGenreWorldError("genre never earned claimed original gameplay event")
            trigger,kind=event
            real_events.append({
                "trace_index":binding["trace_index"],
                "site_id":binding["site_id"],
                "source_action":frame["action"],
                "source_event":trigger,
                "world_kind":kind,
                "original_trace_digest":frame["digest"],
            })
        real_events.sort(key=lambda item:item["trace_index"])
        state=quest_start(world_cfg,world["seed"])
        quest_apply(state,world_cfg,world["layout"])
        ledger=[]
        previous=_sha({"schema":SCHEMA,"source":source["digest"],
                       "world_scene":world["digest"]})
        for event in real_events:
            receipt={
                "source_session_digest":source["digest"],
                "source_editor":source["editor"],
                "source_event":event["source_event"],
                "trace_index":event["trace_index"],
            }
            source_cause=apply_verified_external_gameplay_event(
                state,world_cfg,event["site_id"],receipt,event["world_kind"])
            originated=[q["id"] for q in state["quests"]
                        if q["origin_event"]==source_cause["id"]]
            proof={**event,
                   "world_event":source_cause,
                   "direct_witnesses":list(source_cause["direct_witnesses"]),
                   "original_quests":originated,
                   "real_stock":source_cause["real_world_stock_transferred"],
                   "world_tick":state["tick"]}
            head=_sha({"previous":previous,"source_cause":proof})
            ledger.append({**proof,"previous_hash":previous,"head_hash":head})
            previous=head
        timeline=[]
        for action in world_actions:
            if state["finished"] or state["failed"]:
                raise CrossGenreWorldError("terminal world cannot accept genre event followups")
            events=quest_step(state,world_cfg,action)
            timeline.append({
                "action":action,"tick":state["tick"],"turn":state["turn"],
                "events":list(events),
                "source_quest_ids":[q["id"] for q in state["quests"] if
                                    q["origin_actor"]=="external:genre"],
            })
        report={
            "schema":SCHEMA,"source_editor":source["editor"],
            "source_session_digest":source["digest"],
            "source_scene_digest":scene["digest"],
            "world_scene_digest":world["digest"],
            "bindings":[dict(b) for b in bindings],
            "world_actions":list(world_actions),
            "earned_events":ledger,"followup_timeline":timeline,
            "world_state":state,"head_hash":previous,
            "source_game_files_changed":False,
            "automatic_rewards_approved":False,
            "native_device_certified":False,
            "model_promotion_approved":False,
        }
    except CrossGenreWorldError:
        raise
    except (TypeError,KeyError,ValueError,IndexError) as exc:
        raise CrossGenreWorldError(
            "original farming/sailing/flight or eyewitness world failed independent verification"
        ) from exc
    return {**report,"digest":_sha(report)}


def verify_cross_genre_world(proof,source,world_scene,source_settings=None,
                             world_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise CrossGenreWorldError("source-bound original genre world proof missing")
    try:
        replay=run_cross_genre_world(
            source,world_scene,proof["bindings"],source_settings,
            world_settings,world_actions=proof["world_actions"])
    except (KeyError,TypeError) as exc:
        raise CrossGenreWorldError("invalid original genre event replay source") from exc
    if replay!=proof:
        raise CrossGenreWorldError("cross-genre source event, NPC witness or world reward forged")
    return True


__all__=["SCHEMA","SUPPORTED","MAX_EVENTS","MAX_WORLD_ACTIONS",
         "CrossGenreWorldError","run_cross_genre_world",
         "verify_cross_genre_world"]
