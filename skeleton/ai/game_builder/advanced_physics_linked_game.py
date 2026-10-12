"""Deterministic, opt-in playable progression coupled to reviewed physics encounters.

All original game actions are executed by the canonical genre engine, all
physical actions by the canonical physics engine, and the *linked* progression
is an explicitly separate authority. No original session, map or saved game is
rewritten. No client-provided health/damage/win state is trusted.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import validate_advanced_scene
from .advanced_physics_interop import (
    SUPPORTED, rehearse_physics_encounter, verify_physics_encounter,
)
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.physics_linked_campaign.v1"
MAX_TURNS=24
ABILITIES=("none","brace","repair")
INITIAL_RESOURCES={"platformer":(5,2,5),"racing":(100,3,100),
                   "sandbox":(100,3,100)}
HIT_DAMAGE={"platformer":1,"racing":15,"sandbox":12}
MAX_HIT_DAMAGE={"platformer":2,"racing":25,"sandbox":20}
REPAIR_POINTS={"platformer":1,"racing":20,"sandbox":25}


class LinkedPhysicsError(ValueError):
    """Invalid original source, unreviewed action or forged coupled progression."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _source_vital(editor,state):
    if editor=="platformer":
        return state["health"]
    if editor=="racing":
        return state["engine_integrity"]
    # Sandbox's derived structure is an independent authored *linked-mode*
    # gameplay resource. It is not represented as original sandbox health.
    return 100


def run_linked_physics_game(editor,source_scene,source_settings=None,turns=()):
    if editor not in SUPPORTED:
        raise LinkedPhysicsError("physics-linked gameplay supports only reviewed original families")
    if type(turns) not in (list,tuple) or len(turns)>MAX_TURNS:
        raise LinkedPhysicsError("source and physical commands exceed the coupled-game turn budget")
    try:
        cfg=make_editor_document(editor,source_settings)["settings"]
        original=validate_advanced_scene(source_scene,cfg)
        if original["editor"]!=editor:
            raise LinkedPhysicsError("authored linked game editor/scene mismatch")
        seed=original["seed"]
        source_actions=[]
        source=run_advanced_session(editor,cfg,(),seed=seed,scene=original)
        verify_advanced_session(source,cfg)
        initial,repair_kits,ceiling=INITIAL_RESOURCES[editor]
        vital=min(initial,_source_vital(editor,source["state"]))
        previous_base=_source_vital(editor,source["state"])
        guard=2
        applied=0
        physical_impacts=0
        damage_taken=0
        repaired=0
        active=True
        log=[]
        prev_hash=_digest({
            "schema":SCHEMA,"scene":original["digest"],
            "settings":make_editor_document(editor,source_settings)["digest"],
        })
        for index,command in enumerate(turns):
            if not active:
                raise LinkedPhysicsError("coupled campaign has ended: no postmortem moves")
            if type(command) is not dict or set(command)!={
                "source_action","physical_actions","ability"}:
                raise LinkedPhysicsError("coupled move must contain exactly two audited actions and ability")
            action=command["source_action"]
            physics=command["physical_actions"]
            ability=command["ability"]
            if type(action) is not str or ability not in ABILITIES or type(ability) is not str:
                raise LinkedPhysicsError("unreviewed source action or linked ability")
            if ability=="brace" and guard==0:
                raise LinkedPhysicsError("finite brace charges exhausted")
            if ability=="repair" and repair_kits==0:
                raise LinkedPhysicsError("no repair kits remain")
            source_actions.append(action)
            source=run_advanced_session(editor,cfg,source_actions,
                                        seed=seed,scene=original)
            verify_advanced_session(source,cfg)
            encounter=rehearse_physics_encounter(source,cfg,physics)
            verify_physics_encounter(encounter,source,cfg)
            hits=encounter["observed_fixture_impacts"]
            # Native reference can emit multiple legitimate fixture impacts
            # in one frame; explicit cap prevents a single contact storm from
            # exhausting every campaign resource.
            hits=min(hits,3)
            baseline=_source_vital(editor,source["state"])
            delta=baseline-previous_base
            previous_base=baseline
            if editor!="sandbox":
                vital=min(ceiling,max(0,vital+delta))
            mitigation=1 if ability=="brace" else 0
            if ability=="brace":
                guard-=1
            # Multiple contacts in one physical step are real, but
            # game damage is clamped to a source-defined per-turn budget.
            raw=min(MAX_HIT_DAMAGE[editor],HIT_DAMAGE[editor]*hits)
            damage=max(0,raw-mitigation*HIT_DAMAGE[editor])
            # Repairs cannot turn a contact into a health gain.
            heal=0
            if ability=="repair":
                repair_kits-=1
                if hits==0:
                    heal=min(ceiling-vital,REPAIR_POINTS[editor])
            vital=max(0,min(ceiling,vital-damage+heal))
            damage_taken+=damage
            repaired+=heal
            physical_impacts+=hits
            terminal=vital==0 or source["terminal"]
            status=("defeat" if vital==0 or source["state"]["failed"] else
                    "victory" if source["state"]["finished"] else
                    "active")
            active=not terminal
            note={
                "index":index+1,
                "source_action":action,
                "physical_actions":list(physics),
                "ability":ability,
                "source_digest":source["digest"],
                "physics_digest":encounter["physics_session"]["digest"],
                "encounter_digest":encounter["digest"],
                "contact_count":hits,
                "damage":damage,
                "recovered":heal,
                "vital":vital,
                "guard_remaining":guard,
                "kits_remaining":repair_kits,
                "mode_status":status,
            }
            head=_digest({"previous":prev_hash,"turn":note})
            log.append({**note,"previous_hash":prev_hash,"head_hash":head})
            prev_hash=head
    except LinkedPhysicsError:
        raise
    except (ValueError,KeyError,TypeError) as exc:
        raise LinkedPhysicsError("linked original gameplay or physical authority rejected the action") from exc

    result={
        "schema":SCHEMA,"editor":editor,"seed":seed,
        "source_scene_digest":original["digest"],
        "source_settings_digest":make_editor_document(editor,source_settings)["digest"],
        "source_gameplay_digest":source["digest"],
        "source_state":source["state"],
        "linked_state":{
            "vital":vital,"initial_vital":initial,"vital_ceiling":ceiling,
            "brace_charges":guard,"repair_kits":repair_kits,
            "physical_impacts":physical_impacts,"damage_taken":damage_taken,
            "recovered":repaired,"game_status":status if log else "active",
            "terminal":not active if log else source["terminal"],
        },
        "turns":log,"head_hash":prev_hash,
        "automatic_model_promotion_allowed":False,
        "source_game_file_mutated":False,
        "native_device_verified":False,
    }
    return {**result,"digest":_digest(result)}


def verify_linked_physics_game(proof,scene,settings=None):
    if type(proof) is not dict or proof.get("schema")!=SCHEMA:
        raise LinkedPhysicsError("linked game evidence schema missing")
    if type(proof.get("turns")) is not list:
        raise LinkedPhysicsError("linked game command ledger missing")
    moves=[{
        "source_action":turn["source_action"],
        "physical_actions":turn["physical_actions"],
        "ability":turn["ability"],
    } for turn in proof["turns"]]
    replay=run_linked_physics_game(proof["editor"],scene,settings,moves)
    if replay!=proof:
        raise LinkedPhysicsError("linked gameplay outcome or physical replay evidence was modified")
    return True


__all__=["SCHEMA","MAX_TURNS","ABILITIES","LinkedPhysicsError",
         "run_linked_physics_game","verify_linked_physics_game"]
