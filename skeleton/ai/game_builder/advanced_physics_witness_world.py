"""Verified source-to-NPC eyewitness incident bridge for authored original worlds.

The physics engine cannot mint an incident from a client assertion: only
independently replayed fixture contacts from a *unique* solid original object
may reach the living-world director. Visibility, day/night, obstruction,
rumors, suspicion and quest creation remain under the quest director's actual
source simulation. Player credit is never granted for an external impact.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import verify_advanced_session
from .advanced_physics_interop import (
    rehearse_physics_encounter,verify_physics_encounter,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_quest_director_runtime import (
    start as quest_start,apply_scene as quest_apply,
    step as quest_step,apply_verified_external_physical_incident,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.physical_witness_causality.v1"
MAX_FOLLOWUPS=24


class PhysicalWitnessError(ValueError):
    """Original source, attributed contact or eyewitness outcome invalid."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def run_physical_witness_world(source_session,quest_scene,
                               source_settings=None,quest_settings=None,
                               *,physics_actions=("push:east",)*8,
                               binding=None,world_actions=()):
    if type(binding) is not dict or set(binding)!={"source_id","site_id"}:
        raise PhysicalWitnessError("explicit original-object-to-world-site author binding required")
    if (type(binding["source_id"]) is not int or
        type(binding["site_id"]) is not int or
        not 0<=binding["site_id"]<4):
        raise PhysicalWitnessError("author binding requires one bounded original object and site")
    if (type(world_actions) not in (list,tuple) or
        len(world_actions)>MAX_FOLLOWUPS or
        any(type(item) is not str for item in world_actions)):
        raise PhysicalWitnessError("finite quest followup action list required")
    try:
        source_cfg=make_editor_document(source_session["editor"],source_settings)["settings"]
        world_cfg=make_editor_document("quest_director",quest_settings)["settings"]
        if source_session["scene"] is None:
            raise PhysicalWitnessError("original source must have signed authored scene")
        verify_advanced_session(source_session,source_cfg)
        source_scene=validate_advanced_scene(source_session["scene"],source_cfg)
        authored_world=validate_advanced_scene(quest_scene,world_cfg)
        proof=rehearse_physics_encounter(source_session,source_cfg,physics_actions)
        verify_physics_encounter(proof,source_session,source_cfg)
        solid=[item for item in proof["witnesses"]
               if (item["layer"] & proof["physics_scene"]["layout"]["bodies"][0]["mask"])!=0]
        contacts=proof["observed_fixture_impacts"]
        world=quest_start(world_cfg,authored_world["seed"])
        quest_apply(world,world_cfg,authored_world["layout"])
        incident=None
        if contacts:
            # Fixture ids are not present in baseline Physics event receipts.
            # With >1 solid origin we CANNOT know which source object collided.
            # Refuse, rather than attributing an event to an arbitrary quest.
            if len(solid)!=1 or solid[0]["source_id"]!=binding["source_id"]:
                raise PhysicalWitnessError(
                    "physical collision lacks unique source-object attribution")
            receipt={
                "interop_digest":proof["digest"],
                "source_editor":proof["source_editor"],
                "source_id":binding["source_id"],
            }
            incident=apply_verified_external_physical_incident(
                world,world_cfg,binding["site_id"],receipt,
                impact_severity=min(3,contacts))
        timeline=[]
        for action in world_actions:
            quest_step(world,world_cfg,action)
            timeline.append({
                "action":action,"turn":world["turn"],
                "tick":world["tick"],"events":list(world["events"]),
                "quests_completed":world["quests_completed"],
                "quest_archive":list(world["quest_archive"]),
            })
        direct=(incident["direct_witnesses"] if incident else [])
        linked_quests=[q["id"] for q in world["quests"]
                       if incident is not None and
                       q["origin_event"]==incident["id"]]
        record={
            "schema":SCHEMA,
            "source_editor":source_session["editor"],
            "source_session_digest":source_session["digest"],
            "source_scene_digest":source_scene["digest"],
            "interop_digest":proof["digest"],
            "original_physics_session_digest":proof["physics_session"]["digest"],
            "world_scene_digest":authored_world["digest"],
            "binding":dict(binding),
            "physical_actions":list(physics_actions),
            "world_actions":list(world_actions),
            "actual_source_impacts":contacts,
            "incident":incident,
            "direct_witnesses":list(direct),
            "physical_origin_quest_ids":linked_quests,
            "world_timeline":timeline,
            "world_state":world,
            "original_source_untouched":True,
            "hardware_native_certified":False,
            "automatic_ai_memory_promotion":False,
        }
    except PhysicalWitnessError:
        raise
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise PhysicalWitnessError(
            "original physics or authored NPC world failed independent verification") from exc
    return {**record,"digest":_digest(record)}


def verify_physical_witness_world(proof,source_session,quest_scene,
                                  source_settings=None,quest_settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise PhysicalWitnessError("signed witnessed-physics report required")
    replay=run_physical_witness_world(
        source_session,quest_scene,source_settings,quest_settings,
        physics_actions=proof["physical_actions"],binding=proof["binding"],
        world_actions=proof["world_actions"])
    if proof!=replay:
        raise PhysicalWitnessError("forged physical incident, direct witness, rumor or quest")
    return True


__all__=["SCHEMA","MAX_FOLLOWUPS","PhysicalWitnessError",
         "run_physical_witness_world","verify_physical_witness_world"]
