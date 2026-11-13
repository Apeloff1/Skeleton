"""Independently verify Godot's instrument trace against recorded physics ticks.

The second JSONL stream must agree with canonical source-journal samples for
position, speed, heading, air-relative speed, wind and contacts. No GPS
hardware is accessed. SHA evidence is integrity-only, not GPU/user attestation.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Iterable

from .game_frontier_native_quest_session import NativeQuestSessionError,_sha


_FIELDS=frozenset((
    "schema","authority","scene_candidate_digest","signed_gdd_digest",
    "actor_id","native_tick","fps","world_xyz_m","velocity_xyz_mps",
    "ground_speed_mps","vertical_rate_mps","heading_deg",
    "airflow_xyz_mps","air_relative_speed_mps","contact_count",
))


def _finite(value, *, nonnegative: bool = False) -> float:
    if type(value) not in (int,float) or not math.isfinite(value):
        raise NativeQuestSessionError("instrument observation contains nonfinite or nonnumeric value")
    x=float(value)
    if nonnegative and x<0:
        raise NativeQuestSessionError("instrument physical measure must be nonnegative")
    return x


def _triple(value) -> tuple[float,float,float]:
    if type(value) is not list or len(value)!=3:
        raise NativeQuestSessionError("instrument must contain typed 3D game vector")
    return tuple(_finite(x) for x in value)


def _match(expected: float, measured: float) -> bool:
    return math.isclose(expected,measured,rel_tol=1e-8,abs_tol=1e-5)


def verify_native_instrument_trace(
    journal,lines: Iterable[str], *, actor_id: str,
    scene_candidate_digest: str,expected_airflow_xyz_mps: list,
    expected_fps: int,max_frames: int = 1000000,
) -> dict:
    if (type(actor_id) is not str or not actor_id
        or type(scene_candidate_digest) is not str or len(scene_candidate_digest)!=64
        or type(expected_fps) is not int or expected_fps not in (30,50,60,120)
        or type(max_frames) is not int or not 1<=max_frames<=1000000):
        raise NativeQuestSessionError("bounded source-anchored instrument proof required")
    wind=_triple(expected_airflow_xyz_mps)
    count=0
    vmax=0.
    vertical_min=0.
    vertical_max=0.
    first_actor_source=None
    chain=None
    for raw in lines:
        if type(raw) is not str or len(raw)>32768:
            raise NativeQuestSessionError("oversized or nontext Godot instrument sample")
        try:
            tick=json.loads(raw)
        except (ValueError,TypeError) as exc:
            raise NativeQuestSessionError("instrument JSONL malformed") from exc
        if (type(tick) is not dict or set(tick)!=_FIELDS
            or tick["schema"]!="skeleton.game.godot_native_instrument_sample.v1"
            or tick["authority"]!="independent_native_instrument_observation_not_attested"
            or tick["signed_gdd_digest"]!=journal.gdd.source_digest
            or tick["scene_candidate_digest"]!=scene_candidate_digest
            or tick["actor_id"]!=actor_id or type(tick["native_tick"]) is not int
            or tick["native_tick"]!=count or type(tick["fps"]) is not int
            or tick["fps"]!=expected_fps
            or type(tick["contact_count"]) is not int or tick["contact_count"]<0):
            raise NativeQuestSessionError("instrument tick identity/schema/time mismatch")
        if count>=max_frames:
            raise NativeQuestSessionError("instrument proof exceeded frame budget")
        sample=journal.native_sample(count)
        if (type(sample) is not dict
            or sample.get("scene_candidate_digest")!=scene_candidate_digest
            or sample.get("signed_gdd_digest")!=journal.gdd.source_digest
            or sample.get("native_tick")!=count
            or sample.get("fps")!=expected_fps):
            raise NativeQuestSessionError("independent physics frame absent from canonical journal")
        actors=[a for a in sample["actors"] if a["id"]==actor_id]
        if len(actors)!=1:
            raise NativeQuestSessionError("instrument actor missing from source physics frame")
        actor=actors[0]
        position=_triple(actor["world_xyz_m"])
        velocity=_triple(actor["velocity_xyz_mps"])
        measured_pos=_triple(tick["world_xyz_m"])
        measured_v=_triple(tick["velocity_xyz_mps"])
        measured_wind=_triple(tick["airflow_xyz_mps"])
        if (not all(_match(a,b) for a,b in zip(position,measured_pos))
            or not all(_match(a,b) for a,b in zip(velocity,measured_v))
            or not all(_match(a,b) for a,b in zip(wind,measured_wind))
            or tick["contact_count"]!=actor["contact_count"]):
            raise NativeQuestSessionError("instrument physics position/velocity/wind/contact forged")
        horizontal=math.hypot(velocity[0],velocity[1])
        heading=(math.degrees(math.atan2(velocity[0],velocity[1])) % 360
                 if horizontal>1e-7 else 0.)
        airspeed=math.sqrt(sum((v-w)**2 for v,w in zip(velocity,wind)))
        for key,expected in (
            ("ground_speed_mps",horizontal),
            ("vertical_rate_mps",velocity[2]),
            ("heading_deg",heading),
            ("air_relative_speed_mps",airspeed),
        ):
            got=_finite(tick[key],nonnegative=key!="vertical_rate_mps")
            if not _match(expected,got):
                raise NativeQuestSessionError(
                    "measured game instrument disagrees with independent Godot source: "+key)
        if first_actor_source is None:
            first_actor_source=actor["source_digest"]
        elif actor["source_digest"]!=first_actor_source:
            raise NativeQuestSessionError("instrument source actor changed within session")
        vertical_min=min(vertical_min,velocity[2])
        vertical_max=max(vertical_max,velocity[2])
        vmax=max(vmax,horizontal)
        chain=_sha({"previous":chain,"tick":count,"data":tick,
                    "source_actor_digest":actor["source_digest"]})
        count+=1
    if count<1 or count!=journal.stats()["head"]+1:
        raise NativeQuestSessionError("instrument trace does not cover every canonical source tick")
    report={
        "schema":"skeleton.game.native_instrument_independent_audit.v1",
        "actor_id":actor_id,
        "scene_candidate_digest":scene_candidate_digest,
        "signed_gdd_digest":journal.gdd.source_digest,
        "source_actor_digest":first_actor_source,
        "verified_physics_frames":count,
        "expected_fps":expected_fps,
        "maximum_ground_speed_mps":vmax,
        "min_vertical_rate_mps":vertical_min,
        "max_vertical_rate_mps":vertical_max,
        "instrument_chain_head":chain,
        "authority":"replayed_godot_physics_instrument_evidence_not_real_GPS",
    }
    report["receipt_digest"]=_sha(report)
    return report
