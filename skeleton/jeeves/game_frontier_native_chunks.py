"""Independent source/observed chunk partition verification for Godot captures.

Captures are untrusted telemetry reports, not GPU/physics attestations. The
native exporter records its observed actor positions and chunk membership.
This module independently reconstructs membership, checks exact coverage and
bounds, and emits an immutable, content-addressed comparison receipt.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import math
from typing import Mapping

from .game_frontier_native_dynamics import (
    inspect_native_dynamics, compare_native_dynamics, NativeDynamicsError,
)


from .game_frontier_native_zones import (
    inspect_native_gameplay_zones, NativeZoneError,
)


class NativeChunkError(ValueError):
    pass


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def _point(x: object) -> tuple[float,float,float]:
    if (not isinstance(x,list) or len(x)!=3 or
        any(type(v) not in (float,int) or not math.isfinite(v)
            or abs(v)>1e8 for v in x)):
        raise NativeChunkError("native game XYZ is nonfinite or invalid")
    return float(x[0]),float(x[1]),float(x[2])


def inspect_native_chunks(sample: Mapping, *, expected_chunk_size_m: float = 32.,
                          require_native_partition: bool = False) -> dict:
    """Reconstruct observed chunk memberships; independently compare v2 proof.

    A hashes the original reported actor/chunk source. B calculates partition
    independently and checks no actor missing/duplicated. A successful return
    proves internal consistency of a *client report*, not its native origin.
    """
    if (type(expected_chunk_size_m) not in (int,float) or
        not math.isfinite(expected_chunk_size_m) or
        not .1<=expected_chunk_size_m<=1e5 or
        not isinstance(sample,Mapping)):
        raise NativeChunkError("valid bounded typed source required")
    units=float(expected_chunk_size_m)
    try:
        zone_proof=inspect_native_gameplay_zones(sample)
    except NativeZoneError as exc:
        raise NativeChunkError("reported game zone membership invalid") from exc
    try:
        dynamics=inspect_native_dynamics(sample)
    except NativeDynamicsError as exc:
        raise NativeChunkError("native mass/material/contact telemetry invalid") from exc
    actors=sample.get("actors")
    if not isinstance(actors,list) or not 1<=len(actors)<=256:
        raise NativeChunkError("native game actor count 1..256 required")
    groups=defaultdict(list)
    all_ids=set()
    for actor in actors:
        if not isinstance(actor,Mapping):
            raise NativeChunkError("malformed native source actor")
        name=actor.get("id")
        if type(name) is not str or not name or len(name)>128 or name in all_ids:
            raise NativeChunkError("duplicate/invalid native actor ID")
        all_ids.add(name)
        x,y,z=_point(actor.get("world_xyz_m"))
        _point(actor.get("velocity_xyz_mps"))
        contacts=actor.get("contact_count")
        if contacts is not None and (type(contacts) is not int or
                                    not 0<=contacts<=64):
            raise NativeChunkError("native contact count outside budget")
        kind=actor.get("source_kind")
        if kind is not None and kind not in (
            "native_rigid_reference","generated_source_proxy"):
            raise NativeChunkError("unknown native actor observation kind")
        groups[(math.floor(x/units),math.floor(y/units))].append(name)
    expected=[
        {"chunk_xy":[cx,cy],"actor_ids":sorted(groups[(cx,cy)])}
        for cx,cy in sorted(groups)]
    stored=sample.get("native_chunks")
    if stored is None:
        if require_native_partition:
            raise NativeChunkError("explicit native chunk partition required")
        native_matches=None
    else:
        if (sample.get("native_chunk_size_m")!=units or
            not isinstance(stored,list) or len(stored)>256):
            raise NativeChunkError("native chunk resolution incompatible")
        if stored!=expected:
            raise NativeChunkError("native chunk partition disagrees with actor physics")
        native_matches=True
    source={
        "schema":"skeleton.game.native_chunk_inspection.v1",
        "native_tick":sample.get("native_tick"),
        "fps":sample.get("fps"),
        "source_candidate_digest":sample.get("scene_candidate_digest"),
        "actor_source_digest":_digest(actors),
        "native_partition_digest":_digest(stored) if stored is not None else None,
        "chunk_size_m":units,
        "chunks":expected,"actor_count":len(actors),
        "chunk_count":len(expected),
        "verifier_a_rehashed_native_source":True,
        "verifier_b_partition_exactly_once":len(all_ids)==len(actors),
        "native_partition_confirmed":native_matches,
        "authority":"reported_native_physics_partition_not_GPU_attestation",
    }
    if zone_proof is not None:
        source["native_zone_digest"]=zone_proof["receipt_digest"]
        source["native_zone_occupant_count"]=zone_proof["occupant_count"]
    if dynamics is not None:
        source["native_dynamics_digest"]=dynamics["receipt_digest"]
        source["native_dynamics_verified"]=True
    source["receipt_digest"]=_digest(source)
    return source


def compare_native_chunk_transitions(
    current: Mapping, *,
    previous: Mapping | None = None,
    expected_chunk_size_m: float = 32.,
    max_speed_mps: float = 500.,
) -> dict:
    """Independently compare two reported native fixed-tick scene partitions.

    This second ledger is based on reported Godot physics actors. A recorded
    contact count is observational context, *not* collision impulse/force.
    The source frame double verifier separately enforces all game/GDD laws.
    """
    if (type(max_speed_mps) not in (int,float) or
        not math.isfinite(max_speed_mps) or
        not 0 < max_speed_mps <= 1e5):
        raise NativeChunkError("finite native motion budget required")
    checked=inspect_native_chunks(
        current,expected_chunk_size_m=expected_chunk_size_m,
        require_native_partition="native_chunks" in current)
    older=(inspect_native_chunks(
        previous,expected_chunk_size_m=expected_chunk_size_m,
        require_native_partition="native_chunks" in previous)
        if previous is not None else None)
    if (type(current.get("native_tick")) is not int or
        current["native_tick"]<0 or
        current.get("fps") not in (30,50,60,120)):
        raise NativeChunkError("valid game engine fixed-tick count required")
    if previous is None:
        if current["native_tick"]!=0:
            raise NativeChunkError("native observation chain must start at tick 0")
    else:
        if (type(previous.get("native_tick")) is not int or
            current["native_tick"]!=previous["native_tick"]+1 or
            current.get("fps")!=previous.get("fps") or
            current.get("scene_candidate_digest")!=
                previous.get("scene_candidate_digest") or
            current.get("signed_gdd_digest")!=
                previous.get("signed_gdd_digest")):
            raise NativeChunkError("native frame or signed scene identity drift")
    now={item["id"]:item for item in current["actors"]}
    old={item["id"]:item for item in previous["actors"]} if previous else {}
    if previous is not None and set(now)!=set(old):
        raise NativeChunkError("native actor births/despawns require signed world authority")
    old_cells={
        actor_id:(math.floor(_point(row["world_xyz_m"])[0]/expected_chunk_size_m),
                  math.floor(_point(row["world_xyz_m"])[1]/expected_chunk_size_m))
        for actor_id,row in old.items()
    }
    new_cells={
        actor_id:(math.floor(_point(row["world_xyz_m"])[0]/expected_chunk_size_m),
                  math.floor(_point(row["world_xyz_m"])[1]/expected_chunk_size_m))
        for actor_id,row in now.items()
    }
    actor_changes=[]
    for key in sorted(now):
        record=now[key]
        prev=old.get(key)
        if prev is not None and prev.get("source_digest")!=record.get("source_digest"):
            raise NativeChunkError("native asset identity silently changed")
        xyz=_point(record["world_xyz_m"])
        vel=_point(record["velocity_xyz_mps"])
        speed=math.sqrt(sum(v*v for v in vel))
        if speed>max_speed_mps:
            raise NativeChunkError("observed native speed beyond source budget")
        prior_xyz=_point(prev["world_xyz_m"]) if prev is not None else None
        displacement=(math.dist(xyz,prior_xyz) if prior_xyz is not None else 0.)
        if displacement>max_speed_mps/current["fps"] + .001:
            raise NativeChunkError("native chunk actor moved too far in one tick")
        contact_before=prev.get("contact_count") if prev is not None else None
        contact_after=record.get("contact_count")
        if contact_before is not None and (type(contact_before) is not int or
                                           not 0<=contact_before<=64):
            raise NativeChunkError("previous native contacts invalid")
        actor_changes.append({
            "actor_id":key,"asset_digest":record["source_digest"],
            "from_chunk":list(old_cells[key]) if prev is not None else None,
            "to_chunk":list(new_cells[key]),
            "migrated":bool(prev is not None and old_cells[key]!=new_cells[key]),
            "displacement_m":displacement,
            "speed_mps":speed,
            "contact_count_before":contact_before,
            "contact_count_after":contact_after,
            "contact_count_delta":(
                contact_after-contact_before if
                type(contact_after) is int and type(contact_before) is int
                else None),
            "authority":"reported_native_motion_not_impulse_force",
        })
    transitions=[]
    for coord in sorted(set(old_cells.values())|set(new_cells.values())):
        entered=sorted(key for key in new_cells
                       if new_cells[key]==coord and old_cells.get(key)!=coord)
        exited=sorted(key for key in old_cells
                      if old_cells[key]==coord and new_cells.get(key)!=coord)
        residents=sorted(key for key in new_cells if new_cells[key]==coord)
        if entered or exited or previous is None:
            transitions.append({
                "chunk_xy":list(coord),"entered":entered,"exited":exited,
                "residents":residents,"retired":bool(exited and not residents),
            })
    migrations=sum(bool(e["migrated"]) for e in actor_changes)
    if previous is not None and (
        sum(len(x["entered"]) for x in transitions)!=migrations or
        sum(len(x["exited"]) for x in transitions)!=migrations):
        raise NativeChunkError("native chunk transition flow not conserved")
    root={
        "schema":"skeleton.game.native_chunk_transitions.v1",
        "frame":current["native_tick"],"fps":current["fps"],
        "source_capture_digest":_digest(current),
        "previous_capture_digest":_digest(previous) if previous is not None else None,
        "native_partition_digest":checked["receipt_digest"],
        "previous_partition_digest":older["receipt_digest"] if older else None,
        "scene_candidate_digest":current.get("scene_candidate_digest"),
        "signed_gdd_digest":current.get("signed_gdd_digest"),
        "actor_count":len(now),"migrations":migrations,
        "retired_chunk_count":sum(bool(x["retired"]) for x in transitions),
        "actors":actor_changes,"chunk_transitions":transitions,
        "verifier_a_source_integrity":True,
        "verifier_b_motion_partition_conservation":True,
        "authority":"runtime_sample_consistency_not_native_attestation",
    }
    try:
        zone_proof=inspect_native_gameplay_zones(current,previous=previous)
    except NativeZoneError as exc:
        raise NativeChunkError("native zone event/transition proof invalid") from exc
    if zone_proof is not None:
        root["native_zone_transition_digest"]=zone_proof["receipt_digest"]
        root["native_zone_event_count"]=zone_proof["event_count"]
    try:
        dynamics_delta=compare_native_dynamics(current,previous=previous)
    except NativeDynamicsError as exc:
        raise NativeChunkError("native body dynamics chain invalid") from exc
    if dynamics_delta is not None:
        root["native_dynamics_transition_digest"]=dynamics_delta["receipt_digest"]
        root["native_dynamics_energy_delta_j"]=dynamics_delta["total_kinetic_energy_delta_j"]
    root["receipt_digest"]=_digest(root)
    return root
