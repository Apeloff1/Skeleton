"""Original deterministic two-peer arena input reconciliation, not network transport.

This module gives rollback_compatible an executable reference meaning:
commands from two real participants are run through the exact existing
fighting hitbox, guard, physics and round primitives, rather than trusting
client-submitted character positions or win flags. Predictions are not
evidence. An authoritative late input is accepted only within an
explicitly bounded correction window; the corrected game is fully
reexecuted from the signed source and exact input history.

No sockets, online PvP claims, anti-cheat attestation or hardware-latency
certification are implied by this simulation layer.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_fighting_runtime import (
    ACTIONS,ATTACKS,FightingActionError,_attack,_facing,_move,
    _distance,_round,_turn,start,apply_scene,
)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.fighting_rollback_v1"
MAX_FRAMES=128
MAX_CORRECTIONS=32


class FightingRollbackError(ValueError):
    """Disallowed peer action, over-budget correction or forged source."""


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
         ensure_ascii=True,allow_nan=False).encode("utf-8")).hexdigest()


def _commands(actions,label):
    if type(actions) not in (list,tuple) or not 0<=len(actions)<=MAX_FRAMES:
        raise FightingRollbackError("bounded original "+label+" input log required")
    if any(type(a) is not str or a not in ACTIONS for a in actions):
        raise FightingRollbackError("only registered physical fighting controls accepted")
    return list(actions)


def _perform(state,cfg,side,command,events):
    """Execute one real peer's local input using the original combat kernel."""
    fighter=state["player"] if side=="blue" else state["opponent"]
    enemy=state["opponent"] if side=="blue" else state["player"]
    if command in ATTACKS:
        _attack(state,cfg,fighter,enemy,command,events)
        state["attacks_observed"][side+":"+command]=(
            state["attacks_observed"].get(side+":"+command,0)+1)
        fighter["guard_high"]=False
        fighter["guard_low"]=False
        fighter["parry"]=False
    elif command in ("approach","retreat","dash","backdash","sidestep_up","sidestep_down"):
        toward=_facing(fighter,enemy)
        distance=2 if command in ("dash","backdash") else 1
        if command in ("retreat","backdash"):distance=-distance
        dx=0 if command.startswith("sidestep") else toward*distance
        dy=1 if command=="sidestep_down" else -1 if command=="sidestep_up" else 0
        _move(state,cfg,fighter,dx,dy,events)
    elif command in ("guard_high","guard_low"):
        fighter["guard_high"]=command=="guard_high"
        fighter["guard_low"]=command=="guard_low"
        fighter["parry"]=False
        events.append("peer_guard_posture_executed_on_original_fighter")
    elif command=="parry":
        if fighter["stamina"]<cfg["parry_stamina"]:
            raise FightingRollbackError("authenticated original peer lacks parry stamina")
        fighter["stamina"]-=cfg["parry_stamina"]
        fighter["parry"]=True
        events.append("peer_spent_finite_stamina_on_precise_parry")
    elif command=="jump":
        if fighter["stamina"]<cfg["jump_stamina"]:
            raise FightingRollbackError("authenticated original peer lacks jump stamina")
        fighter["stamina"]-=cfg["jump_stamina"]
        fighter["airborne"]=cfg["jump_duration_frames"]
        fighter["guard_low"]=False
        events.append("peer_executed_original_spatial_airborne_evasion")
    elif command=="crouch":
        fighter["crouching"]=True;fighter["airborne"]=0
        events.append("peer_original_fighter_crouched")
    elif command=="stand":
        fighter["crouching"]=False
        events.append("peer_original_fighter_stood")
    elif command=="dodge":
        fighter["parry"]=False
        if _distance(fighter,enemy)<=2:
            _move(state,cfg,fighter,-_facing(fighter,enemy),0,events)
        events.append("peer_attempted_real_physical_evasion")
    elif command=="charge":
        fighter["meter"]=min(cfg["meter_cap"],fighter["meter"]+cfg["charge_meter"])
        events.append("peer_spent_real_turn_charging_finite_meter")
    elif command=="recover":
        fighter["stamina"]=min(fighter["max_stamina"],
                               fighter["stamina"]+cfg["recover_stamina"])
        events.append("peer_spent_real_turn_recovering_finite_energy")
    elif command=="feint":
        if fighter["stamina"]<cfg["feint_stamina"]:
            raise FightingRollbackError("insufficient real stamina for peer feint")
        fighter["stamina"]-=cfg["feint_stamina"]
        enemy["guard_high"]=False;enemy["guard_low"]=False
        events.append("peer_paid_real_stamina_for_guard_breaking_feint")
    elif command in ("wait:60","wait:240","inspect"):
        events.append("peer_executed_authoritative_no_hit_or_clock_input")
    else:
        raise FightingRollbackError("no bounded original implementation for peer action")


def run_peer_fight(settings=None,blue_actions=(),red_actions=(),*,
                   seed=0,scene=None):
    """Reexecute both authenticated peers from the original signed arena.

    Frames alternate initial execution priority. Both commands incur their
    actual combat costs, collisions, recovery frames and terminal handling.
    Neither player is a scripted NPC. A true round result is produced only
    by physical damage, real ringout, hazards or elapsed round timeout.
    """
    blue=_commands(blue_actions,"blue")
    red=_commands(red_actions,"red")
    if len(blue)!=len(red):
        raise FightingRollbackError("both peer streams require one input per frame")
    if type(seed) is not int or not 0<=seed<=2**31-1:
        raise FightingRollbackError("original match seed must be bounded integer")
    cfg=make_editor_document("fighting",settings)
    rules=cfg["settings"]
    if not rules["rollback_compatible"]:
        raise FightingRollbackError("author rejected rollback compatibility for this fighting mode")
    source=None
    if scene is not None:
        source=validate_advanced_scene(scene,rules)
        if source["editor"]!="fighting" or source["seed"]!=seed:
            raise FightingRollbackError("original authored arena source and seed mismatch")
    state=start(rules,seed)
    if source is not None:
        apply_scene(state,rules,source["layout"])
    context={
        "schema":SCHEMA,"seed":seed,"settings_digest":cfg["digest"],
        "scene_digest":source["digest"] if source else None,
        "peer_mode":"two_authoritative_players_not_scripted_ai",
        "order":"alternating_frame_priority",
        "rollback_authorized":True,
    }
    head=_digest(context)
    trace=[]
    for frame,(a,b) in enumerate(zip(blue,red)):
        if state["finished"] or state["failed"]:
            raise FightingRollbackError("cannot issue actions after real arena match is terminal")
        events=[]
        first=("blue","red") if frame%2==0 else ("red","blue")
        current_round=state["round"]
        try:
            for side in first:
                if state["finished"] or state["failed"] or state["round"]!=current_round:
                    break
                _perform(state,rules,side,a if side=="blue" else b,events)
                _round(state,rules,events)
            if not state["finished"] and not state["failed"] and state["round"]==current_round:
                # A paired command is a deterministic input *step*. Actual
                # elapsed simulation frames honor either participant's
                # explicit bounded wait duration; short steps retain the
                # game's authored standard frame cadence.
                advance=max([rules["frames_per_turn"]]+[
                    int(move.split(":")[1]) for move in (a,b)
                    if move.startswith("wait:")
                ])
                _turn(state,rules,events,advance)
        except (FightingActionError,FightingRollbackError) as exc:
            raise FightingRollbackError(
                "original peer input invalid at frame "+str(frame)+": "+str(exc)
            ) from exc
        state["turn"]+=1
        state["events"]=events
        fragment={
            "frame":frame,"blue":a,"red":b,
            "clock_frames":state["clock_frames"],
            "priority":first[0],"events_digest":_digest(events),
            "state_digest":_digest(state),"previous_digest":head,
        }
        fragment["digest"]=_digest(fragment)
        trace.append(fragment)
        head=fragment["digest"]
    record={
        **context,"source":source,"blue_actions":blue,"red_actions":red,
        "frames":len(blue),"trace":trace,"head_digest":head,
        "state":state,"terminal":state["finished"] or state["failed"],
        "actual_player_victory":state["victory"],
        "network_transport_certified":False,
        "live_peer_identity_certified":False,
        "hardware_controller_latency_verified":False,
        "untrusted_network_state_accepted":False,
    }
    return {**record,"digest":_digest(record)}


def verify_peer_fight(record,settings=None):
    if type(record) is not dict or record.get("schema")!=SCHEMA:
        raise FightingRollbackError("canonical original peer source required")
    replay=run_peer_fight(
        settings,record.get("blue_actions"),record.get("red_actions"),
        seed=record.get("seed"),scene=record.get("source"))
    if replay!=record:
        raise FightingRollbackError("peer action trace, score, world or source has been forged")
    return True


def reconcile_peer_prediction(settings,blue_actions,remote_predictions,
                              remote_authoritative,*,seed=0,scene=None):
    """Validate a bounded late remote correction and rebuild the actual match.

    A returned predicted state is for UX comparison only, never authority.
    Remote corrections older than the final configured rollback window are
    rejected, even if the remote claims an existing snapshot is trusted.
    """
    cfg=make_editor_document("fighting",settings)
    rules=cfg["settings"]
    if not rules["rollback_compatible"]:
        raise FightingRollbackError("rollback input correction disabled by authored editor")
    blue=_commands(blue_actions,"blue")
    estimated=_commands(remote_predictions,"predicted remote")
    authoritative=_commands(remote_authoritative,"authoritative remote")
    if len(blue)!=len(estimated) or len(blue)!=len(authoritative):
        raise FightingRollbackError("peer input histories require exact frame alignment")
    corrections=[i for i,(a,b) in enumerate(zip(estimated,authoritative)) if a!=b]
    window=rules["rollback_window_frames"]
    if len(corrections)>min(MAX_CORRECTIONS,rules["max_rollback_corrections"]):
        raise FightingRollbackError("original netcode correction budget exceeded")
    if any(len(blue)-index>window for index in corrections):
        raise FightingRollbackError("unconfirmed remote input aged outside bounded rollback window")
    predicted=run_peer_fight(rules,blue,estimated,seed=seed,scene=scene)
    actual=run_peer_fight(rules,blue,authoritative,seed=seed,scene=scene)
    proof={
        "schema":"skeleton.game_builder.fighting_rollback_correction_v1",
        "seed":seed,"settings_digest":cfg["digest"],
        "source":actual["source"],"blue_actions":blue,
        "predicted_remote":estimated,
        "authoritative_remote":authoritative,
        "reconciled_indices":corrections,
        "rollback_window_frames":window,
        "predicted_match_digest":predicted["digest"],
        "authoritative_match":actual,
        "prediction_is_authoritative":False,
        "remote_client_state_trusted":False,
        "network_transport_certified":False,
    }
    return {**proof,"digest":_digest(proof)}


def verify_peer_reconciliation(record,settings=None):
    if type(record) is not dict or record.get("schema")!=(
        "skeleton.game_builder.fighting_rollback_correction_v1"):
        raise FightingRollbackError("exact two-peer correction proof required")
    replay=reconcile_peer_prediction(
        settings,record.get("blue_actions"),record.get("predicted_remote"),
        record.get("authoritative_remote"),seed=record.get("seed"),
        scene=record.get("source"))
    if replay!=record:
        raise FightingRollbackError("remote input correction chain or authoritative match was tampered")
    return True


__all__=["SCHEMA","MAX_FRAMES","FightingRollbackError",
         "run_peer_fight","verify_peer_fight",
         "reconcile_peer_prediction","verify_peer_reconciliation"]
