"""Bounded native gameplay force fields and independently replayed force receipts.

These are actual authored reference-body forces: updraft, downdraft, horizontal
current and vortex. A reported prior-step force must match the *previous*
recorded body position and mass, preventing an arbitrary engine-provided force
from being presented as a verified source force. It does not attest the native
solver's integration result or the accuracy of the Godot physical simulation.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Mapping

SCHEMA = "skeleton.game.native_force_fields.v1"
KINDS = frozenset(("updraft", "downdraft", "eastward_current", "vortex"))
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class NativeForceFieldError(ValueError):
    pass


def _number(value: object, low: float, high: float) -> float:
    if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
        raise NativeForceFieldError("bounded finite native force field quantity required")
    return float(value)


def _hash(value: object) -> str:
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def normalize_native_force_fields(
    raw: object, *, allowed_actors: set[str] | None = None,
) -> list[dict]:
    if not isinstance(raw,(tuple,list)) or len(raw)>64:
        raise NativeForceFieldError("at most 64 explicit native fields")
    catalog=[]
    seen=set()
    for item in raw:
        if not isinstance(item,Mapping) or set(item)!={
            "id","actor_id","kind","center_xyz_m","radius_m","acceleration_mps2",
        }:
            raise NativeForceFieldError("complete native field source schema required")
        ident=item["id"]
        actor=item["actor_id"]
        if (type(ident) is not str or not _ID.fullmatch(ident)
            or type(actor) is not str or not _ID.fullmatch(actor)
            or ident in seen or
            allowed_actors is not None and actor not in allowed_actors):
            raise NativeForceFieldError("duplicate or unauthorized field actor/ID")
        if item["kind"] not in KINDS:
            raise NativeForceFieldError("unknown native game force field type")
        coords=item["center_xyz_m"]
        if not isinstance(coords,(tuple,list)) or len(coords)!=3:
            raise NativeForceFieldError("3D authored force center required")
        catalog.append({
            "id":ident,"actor_id":actor,"kind":item["kind"],
            "center_xyz_m":[round(_number(v,-1e6,1e6),3) for v in coords],
            "radius_m":round(_number(item["radius_m"],.1,10000.),3),
            "acceleration_mps2":round(
                _number(item["acceleration_mps2"],0.,25.),3),
        })
        seen.add(ident)
    return sorted(catalog,key=lambda row:row["id"])


def calculated_native_field_force(
    field: Mapping, position_xyz_m: list | tuple, mass_kg: float,
) -> tuple[float,float,float]:
    if not isinstance(position_xyz_m,(tuple,list)) or len(position_xyz_m)!=3:
        raise NativeForceFieldError("real previous frame position required")
    coords=tuple(_number(v,-1e8,1e8) for v in position_xyz_m)
    mass=_number(mass_kg,0.,1e6)
    dx=coords[0]-field["center_xyz_m"][0]
    dy=coords[1]-field["center_xyz_m"][1]
    dz=coords[2]-field["center_xyz_m"][2]
    radius=field["radius_m"]
    squared=dx*dx+dy*dy+dz*dz
    taper=max(0.,1.-squared/(radius*radius))
    effective=mass*field["acceleration_mps2"]*taper
    kind=field["kind"]
    if kind=="updraft":
        return 0.,0.,effective
    if kind=="downdraft":
        return 0.,0.,-effective
    if kind=="eastward_current":
        return effective,0.,0.
    planar=math.hypot(dx,dy)
    if planar<=1e-9:
        return 0.,0.,0.
    return -dy/planar*effective,dx/planar*effective,0.


def inspect_native_force_fields(
    sample: Mapping, *, previous: Mapping | None = None,
    expected_catalog: object | None = None,
) -> dict | None:
    """Require exact field catalog and one prior-position-bound force per field."""
    if not isinstance(sample,Mapping):
        raise NativeForceFieldError("reported native frame must be a mapping")
    present=any(key in sample for key in (
        "native_force_field_schema","native_force_fields","previous_step_field_forces"))
    authored=normalize_native_force_fields(expected_catalog) if expected_catalog is not None else None
    if not present:
        if authored or previous is not None and "native_force_field_schema" in previous:
            raise NativeForceFieldError("native field telemetry disappeared")
        return None
    if sample.get("native_force_field_schema")!=SCHEMA:
        raise NativeForceFieldError("wrong source native field schema")
    actual=normalize_native_force_fields(sample.get("native_force_fields"))
    if not actual or authored is not None and actual!=authored:
        raise NativeForceFieldError("reported field differs from authored source")
    actors=sample.get("actors")
    if not isinstance(actors,list) or not 1<=len(actors)<=256:
        raise NativeForceFieldError("native actor list invalid")
    by_actor={row.get("id"):row for row in actors if isinstance(row,Mapping)}
    if len(by_actor)!=len(actors) or any(x["actor_id"] not in by_actor for x in actual):
        raise NativeForceFieldError("native field actor missing")
    tick=sample.get("native_tick")
    if type(tick) is not int or tick<0:
        raise NativeForceFieldError("native field tick required")
    command=sample.get("previous_step_field_forces")
    if not isinstance(command,list):
        raise NativeForceFieldError("native force-step receipt list required")
    if previous is not None:
        if previous.get("native_force_field_schema")!=SCHEMA or (
            normalize_native_force_fields(previous.get("native_force_fields"))!=actual):
            raise NativeForceFieldError("native force field roster changed mid-session")
        if tick!=previous.get("native_tick",-2)+1:
            raise NativeForceFieldError("native force step sequence gap")
    if tick==0:
        if command:
            raise NativeForceFieldError("initial field step must be empty")
    else:
        if len(command)!=len(actual):
            raise NativeForceFieldError("a field-step receipt missing or duplicated")
        for index,field in enumerate(actual):
            result=command[index]
            if (not isinstance(result,dict) or set(result)!={
                "field_id","actor_id","command_tick",
                "source_position_xyz_m","force_world_xyz_n"} or
                result["field_id"]!=field["id"] or
                result["actor_id"]!=field["actor_id"] or
                type(result["command_tick"]) is not int or
                result["command_tick"]!=tick-1):
                raise NativeForceFieldError("wrong or incomplete force event identity")
            vec=result["force_world_xyz_n"]
            pos=result["source_position_xyz_m"]
            if (not isinstance(vec,list) or len(vec)!=3 or
                not isinstance(pos,list) or len(pos)!=3):
                raise NativeForceFieldError("force vector/position schema invalid")
            if previous is not None:
                body=next(a for a in previous["actors"] if a["id"]==field["actor_id"])
                reported_position=body["world_xyz_m"]
                if any(not math.isclose(
                    _number(x,-1e8,1e8),float(y),abs_tol=.005,rel_tol=0)
                    for x,y in zip(pos,reported_position)):
                    raise NativeForceFieldError("field input position not from previous fixed tick")
                physical=body.get("physics_body")
                if not isinstance(physical,dict) or physical.get("mode")!="rigid":
                    raise NativeForceFieldError("field recipient must be observed RigidBody3D")
                expected=calculated_native_field_force(
                    field,reported_position,physical["mass_kg"])
                if any(not math.isclose(
                    _number(value,-1e8,1e8),force,abs_tol=.01,rel_tol=.001)
                    for value,force in zip(vec,expected)):
                    raise NativeForceFieldError("reported force does not follow authored field")
            else:
                for x in (*vec,*pos):
                    _number(x,-1e8,1e8)
    report={
        "schema":"skeleton.game.native_field_inspection.v1",
        "native_tick":tick,
        "source_gdd_digest":sample.get("signed_gdd_digest"),
        "scene_candidate_digest":sample.get("scene_candidate_digest"),
        "fields_digest":_hash(actual),
        "previous_step_receipts_digest":_hash(command),
        "step_force_count":len(command),
        "previous_source_verified":previous is not None or tick==0,
        "authority":"source_bound_reported_forces_not_solver_attestation",
    }
    report["receipt_digest"]=_hash(report)
    return report
