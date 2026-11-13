"""Independent verification of reported Godot reference-player controls.

Inputs are optional and never replace signed GDD/scene authority. The headless
fixture is explicitly generated and not evidence of human play or NPC AI.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Mapping


class NativeControlError(ValueError):
    pass


def _number(value: object, lo: float, hi: float) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
        raise NativeControlError("nonfinite or unbounded reference control parameter")
    return float(value)


def verify_native_reference_input(
    sample: Mapping,
    controls: Mapping | None,
    *,
    actor_id: str,
) -> dict | None:
    """Check exact actor/tick/force provenance, including deterministic fixture.

    The command at capture frame N describes what was applied *after* frame
    N-1 was observed. Frame zero has no preceding controller action.
    """
    if not isinstance(sample, Mapping) or type(actor_id) is not str or not actor_id:
        raise NativeControlError("valid native sample and authorized actor ID required")
    if controls is None:
        if "previous_step_control" in sample:
            raise NativeControlError("unconfigured native controller telemetry")
        return None
    if not isinstance(controls, Mapping):
        raise NativeControlError("typed source control configuration required")
    enabled=controls.get("enabled")
    if type(enabled) is not bool:
        raise NativeControlError("explicit controller enabled flag required")
    if not enabled:
        if "previous_step_control" in sample:
            raise NativeControlError("disabled controller emitted input receipt")
        return None
    tick=sample.get("native_tick")
    fixture=controls.get("headless_fixture_ticks",0)
    if type(tick) is not int or tick<0 or type(fixture) is not int or not 0<=fixture<=64:
        raise NativeControlError("invalid control sequence/tick")
    force_limit=_number(controls.get("move_force_n"),.001,5000.)
    _number(controls.get("max_speed_mps"),.1,50.)
    impulse_limit=_number(controls.get("jump_impulse_ns"),0.,2000.)
    input_data=sample.get("previous_step_control")
    if tick==0:
        if input_data!={}:
            raise NativeControlError("initial Godot control receipt must be empty")
        return {"frame":0,"source":"initial_no_input","applied_force_n":0.}
    required={"schema","actor_id","command_tick","input_kind","input_axis_xy",
              "force_world_xyz_n","jump_impulse_ns",
              "bounded_reference_controller_not_NPC_AI"}
    if not isinstance(input_data,dict) or set(input_data)!=required:
        raise NativeControlError("complete typed reference control receipt required")
    if (input_data["schema"]!="skeleton.game.native_reference_input.v1" or
        input_data["actor_id"]!=actor_id or
        type(input_data["command_tick"]) is not int or
        input_data["command_tick"]!=tick-1 or
        input_data["bounded_reference_controller_not_NPC_AI"] is not True):
        raise NativeControlError("reference input actor, version, origin or tick invalid")
    kind=input_data["input_kind"]
    if kind not in ("none","human_input","headless_fixture"):
        raise NativeControlError("reference input provenance invalid")
    axis=input_data["input_axis_xy"]
    applied=input_data["force_world_xyz_n"]
    if (not isinstance(axis,list) or len(axis)!=2 or
        not isinstance(applied,list) or len(applied)!=3):
        raise NativeControlError("reference axis and world force shape invalid")
    ax=tuple(_number(x,-1.,1.) for x in axis)
    vec=tuple(_number(x,-5000.,5000.) for x in applied)
    jump=_number(input_data["jump_impulse_ns"],0.,impulse_limit)
    if math.hypot(*ax)>1.00001:
        raise NativeControlError("reference analog input vector is unnormalized")
    nominal=(ax[0]*force_limit,-ax[1]*force_limit,0.)
    if (not all(math.isclose(a,b,rel_tol=1e-5,abs_tol=1e-5)
                for a,b in zip(vec,nominal)) and
        not all(abs(x)<1e-7 for x in vec)):
        raise NativeControlError("reported native movement force disagrees with source controller")
    if kind=="none" and (any(abs(a)>1e-8 for a in ax) or any(abs(v)>1e-8 for v in vec)):
        raise NativeControlError("no-input controller reported movement force")
    if kind=="human_input" and all(abs(a)<1e-8 for a in ax):
        raise NativeControlError("human movement label without movement axis")
    if tick-1<fixture:
        if (kind!="headless_fixture" or ax!=(1.,0.) or jump!=0. or
            not all(math.isclose(a,b,abs_tol=1e-5)
                    for a,b in zip(vec,(force_limit,0.,0.)))):
            raise NativeControlError("expected headless fixture force was not applied")
    elif kind=="headless_fixture":
        raise NativeControlError("headless commands leaked after bounded fixture")
    result={"frame":tick,"actor_id":actor_id,"source":kind,
            "applied_force_n":math.sqrt(sum(x*x for x in vec)),
            "jump_impulse_ns":jump,
            "reference_only_not_playthrough_proof":True}
    return result
