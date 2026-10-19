"""Source-bound gameplay trigger volumes over observed Godot fixed-step positions.

The engine emits enter/exit candidate RPG proposals. This independent verifier
reconstructs occupants from actual reported game XYZ, checks fixed source
zones, transitions and event page provenance. Neither proposals nor receipts
dispatch a quest, teleport, edit GDD canon or execute model-written code.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Mapping

ZONE_SCHEMA = "skeleton.game.native_zones.v1"
EVENT_AUTHORITY = "proposal_only_no_world_mutation"
ACTION_KINDS = frozenset((
    "show_dialogue", "save_bookmark", "start_quest", "advance_quest",
    "trigger_impact_fx", "spatial_audio", "inspect_instrument",
))
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class NativeZoneError(ValueError):
    pass


def _hash(obj: object) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _number(value: object, minimum: float, maximum: float) -> float:
    if (type(value) not in (int,float) or not math.isfinite(value)
            or not minimum <= value <= maximum):
        raise NativeZoneError("invalid bounded native gameplay zone coordinate")
    return float(value)


def normalize_gameplay_zones(zones: object,
                             *, allowed_actors: set[str] | None = None) -> list[dict]:
    """Strict source schema shared by Forge exporter and native verifier."""
    if not isinstance(zones, (tuple,list)) or len(zones)>64:
        raise NativeZoneError("at most 64 explicit authored trigger zones permitted")
    result=[]
    seen=set()
    for zone in zones:
        required={"id","actor_id","center_xyz_m","radius_m","event_page_id","action_kind"}
        if not isinstance(zone,Mapping) or set(zone)!=required:
            raise NativeZoneError("complete source zone descriptor required")
        for key in ("id","actor_id","event_page_id"):
            val=zone[key]
            if type(val) is not str or not _ID.fullmatch(val):
                raise NativeZoneError("invalid trigger, actor or event page identity")
        if zone["id"] in seen:
            raise NativeZoneError("duplicate native gameplay zone")
        if allowed_actors is not None and zone["actor_id"] not in allowed_actors:
            raise NativeZoneError("zone actor not found in signed source actors")
        if zone["action_kind"] not in ACTION_KINDS:
            raise NativeZoneError("unsafe or unsupported gameplay action")
        center=zone["center_xyz_m"]
        if not isinstance(center,(tuple,list)) or len(center)!=3:
            raise NativeZoneError("finite source trigger center XYZ required")
        result.append({
            "id":zone["id"],
            "actor_id":zone["actor_id"],
            "center_xyz_m":[_number(c,-1e6,1e6) for c in center],
            "radius_m":_number(zone["radius_m"],.1,10000.),
            "event_page_id":zone["event_page_id"],
            "action_kind":zone["action_kind"],
        })
        seen.add(zone["id"])
    return sorted(result,key=lambda z:z["id"])


def _occupancy(sample: Mapping, zones: list[dict]) -> list[dict]:
    actors=sample.get("actors")
    if not isinstance(actors,list) or not 1<=len(actors)<=256:
        raise NativeZoneError("bounded native actor source required")
    positions={}
    for row in actors:
        if not isinstance(row,Mapping):
            raise NativeZoneError("malformed native actor")
        name=row.get("id")
        xyz=row.get("world_xyz_m")
        if (type(name) is not str or name in positions or
            not isinstance(xyz,list) or len(xyz)!=3):
            raise NativeZoneError("duplicate actor or missing reported position")
        positions[name]=tuple(_number(v,-1e8,1e8) for v in xyz)
    inside=[]
    for zone in zones:
        target=positions.get(zone["actor_id"])
        if target is None:
            raise NativeZoneError("signed zone actor missing from native sample")
        delta=sum((a-b)**2 for a,b in zip(target,zone["center_xyz_m"]))
        if delta <= zone["radius_m"]**2:
            inside.append({"zone_id":zone["id"],"actor_id":zone["actor_id"]})
    return inside


def inspect_native_gameplay_zones(
    sample: Mapping, *,
    expected_catalog: object | None = None,
    previous: Mapping | None = None,
) -> dict | None:
    """Reject altered occupancy and crossing receipts, not just their hashes.

    Without a previous frame, transition verification is defined at tick 0;
    later standalone reads still independently verify full zone occupancy.
    Full chained verification uses the prior observed fixed-step sample.
    """
    if not isinstance(sample,Mapping):
        raise NativeZoneError("typed reported native sample required")
    has_zones=any(key in sample for key in (
        "native_zone_schema","gameplay_zones","native_zone_occupancy","native_zone_events"))
    if not has_zones:
        if expected_catalog is not None and normalize_gameplay_zones(expected_catalog):
            raise NativeZoneError("missing source-authorized native gameplay zones")
        if previous is not None and "native_zone_schema" in previous:
            raise NativeZoneError("native zone telemetry disappeared mid-session")
        return None
    if sample.get("native_zone_schema")!=ZONE_SCHEMA:
        raise NativeZoneError("invalid gameplay zone schema")
    zones=normalize_gameplay_zones(sample.get("gameplay_zones"))
    if not zones:
        raise NativeZoneError("enabled zone telemetry requires authored volumes")
    ids={row.get("id") for row in sample.get("actors",[]) if isinstance(row,Mapping)}
    if any(zone["actor_id"] not in ids for zone in zones):
        raise NativeZoneError("zone does not belong to observed source actor")
    if expected_catalog is not None and zones!=normalize_gameplay_zones(expected_catalog):
        raise NativeZoneError("reported gameplay zone catalog differs from authored scene")
    now=_occupancy(sample,zones)
    if sample.get("native_zone_occupancy")!=now:
        raise NativeZoneError("engine zone membership disagrees with source geometry")
    prior=[]
    if previous is not None:
        if previous.get("native_zone_schema")!=ZONE_SCHEMA:
            raise NativeZoneError("native zone source appeared after frame zero")
        if normalize_gameplay_zones(previous.get("gameplay_zones"))!=zones:
            raise NativeZoneError("authored game zone catalog changed during capture")
        prior=_occupancy(previous,zones)
        if previous.get("native_zone_occupancy")!=prior:
            raise NativeZoneError("prior gameplay zone membership corrupted")
    tick=sample.get("native_tick")
    if type(tick) is not int or tick<0:
        raise NativeZoneError("native gameplay zone frame index required")
    if previous is not None and tick!=previous.get("native_tick",-2)+1:
        raise NativeZoneError("zone sequence discontinuity")
    events=[]
    if previous is not None or tick==0:
        zone_by_id={z["id"]:z for z in zones}
        for record in now:
            if record not in prior:
                zone=zone_by_id[record["zone_id"]]
                events.append({
                    **record,"transition":"enter",
                    "event_page_id":zone["event_page_id"],
                    "action_kind":zone["action_kind"],
                    "authority":EVENT_AUTHORITY,
                })
        for record in prior:
            if record not in now:
                zone=zone_by_id[record["zone_id"]]
                events.append({
                    **record,"transition":"exit",
                    "event_page_id":zone["event_page_id"],
                    "action_kind":zone["action_kind"],
                    "authority":EVENT_AUTHORITY,
                })
        events.sort(key=lambda e:(e["zone_id"],e["actor_id"],e["transition"]))
        if sample.get("native_zone_events")!=events:
            raise NativeZoneError("native zone entry/exit events inconsistent with observed motion")
    elif not isinstance(sample.get("native_zone_events"),list):
        raise NativeZoneError("native gameplay zone events required")
    receipt={
        "schema":"skeleton.game.native_zone_inspection.v1",
        "native_tick":tick,
        "signed_gdd_digest":sample.get("signed_gdd_digest"),
        "scene_candidate_digest":sample.get("scene_candidate_digest"),
        "zones_digest":_hash(zones),
        "occupancy_digest":_hash(now),
        "events_digest":_hash(sample["native_zone_events"]),
        "occupant_count":len(now),
        "event_count":len(sample["native_zone_events"]),
        "transition_verified":previous is not None or tick==0,
        "previous_native_source_digest":_hash(previous) if previous is not None else None,
        "authority":EVENT_AUTHORITY,
    }
    receipt["receipt_digest"]=_hash(receipt)
    return receipt
