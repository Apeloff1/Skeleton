"""Bounded, replay-verified runtime diagnostics for native game-physics capture.

Read-only analyzer of one signed GDD journal track. Computes displacement,
accelerations, energy and contact episodes from *reported* fixed-tick samples.
Flags candidate review events; it never claims observed collision forces,
visual GPU correctness, native attestation or authentic NPC behavior.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game_frontier_receipt_journal import FrameReceiptJournal


class NativeAuditError(ValueError):
    pass


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def analyze_native_capture(
    journal: FrameReceiptJournal,
    *, start_frame: int = 0,
    max_frames: int = 256,
    actor_id: str | None = None,
    acceleration_threshold_mps2: float = 120.,
    energy_change_threshold_j: float = 2000.,
) -> dict:
    """Full-prefix verification precedes bounded analysis of a chosen window.

    Sampling a prefix without replay would miss a corrupted predecessor;
    always validate the full replay chain up through the selected window.
    There is no implicit mutation of canon or of the journal.
    """
    from .game_frontier_receipt_journal import FrameReceiptJournal
    from .game_frontier_native_dynamics import inspect_native_dynamics
    if not isinstance(journal, FrameReceiptJournal):
        raise NativeAuditError("durable signed source journal required")
    if (type(start_frame) is not int or start_frame < 0
            or type(max_frames) is not int or not 1 <= max_frames <= 4096
            or actor_id is not None and (
                type(actor_id) is not str or not 1 <= len(actor_id) <= 128)
            or type(acceleration_threshold_mps2) not in (int, float)
            or not math.isfinite(acceleration_threshold_mps2)
            or not 0 < acceleration_threshold_mps2 <= 1e5
            or type(energy_change_threshold_j) not in (int, float)
            or not math.isfinite(energy_change_threshold_j)
            or not 0 < energy_change_threshold_j <= 1e12):
        raise NativeAuditError("invalid bounded native audit selection/threshold")
    head=journal.stats()["head"]
    if start_frame > head:
        raise NativeAuditError("source journal has no frames at selected cursor")
    last=min(head, start_frame + max_frames - 1)
    prior_replay=journal.replay(through=last)
    positions={}
    results={}
    anomalies=[]
    samples=[]
    evidence=[]
    for index in range(start_frame,last+1):
        native=journal.native_sample(index)
        if native is None:
            raise NativeAuditError("native audit requires complete observed frame series")
        frame,_=journal.load(index)
        journal._validate_native_sample(frame,native)
        partition=journal.native_chunk_evidence(index)
        transition=journal.native_chunk_transitions(index)
        dynamics=journal.native_dynamics_evidence(index)
        if partition is None or transition is None:
            raise NativeAuditError("missing committed native chunk/transition evidence")
        samples.append(_digest(native))
        evidence.append((frame.receipt_digest,partition["receipt_digest"],
                         transition["receipt_digest"],
                         dynamics["receipt_digest"] if dynamics else None))
        energy={row["id"]:row["kinetic_energy_j"]
                for row in dynamics["actors"]} if dynamics else {}
        from .game_frontier_native_fields import inspect_native_force_fields
        field_proof=inspect_native_force_fields(
            native,previous=journal.native_sample(index-1) if index else None)
        game_field_forces={}
        if field_proof is not None:
            for item in native["previous_step_field_forces"]:
                magnitude=math.dist([0.,0.,0.],item["force_world_xyz_n"])
                key=item["actor_id"]
                game_field_forces[key]=game_field_forces.get(key,0.)+magnitude
        for actor in native["actors"]:
            name=actor["id"]
            if actor_id is not None and name!=actor_id:
                continue
            position=tuple(float(x) for x in actor["world_xyz_m"])
            velocity=tuple(float(x) for x in actor["velocity_xyz_mps"])
            speed=math.sqrt(sum(v*v for v in velocity))
            count=actor.get("contact_count")
            if type(count) is not int:
                count=None
            state=results.setdefault(name,{
                "id":name,"source_digest":actor["source_digest"],
                "samples":0,"path_distance_m":0.,"net_displacement_m":0.,
                "max_reported_speed_mps":0.,"peak_estimated_acceleration_mps2":0.,
                "max_height_m":position[2],"min_height_m":position[2],
                "peak_reported_kinetic_energy_j":None,
                "positive_contact_ticks":0,"contact_change_events":0,
                "chunk_migrations":0,"event_count":0,
                "positive_gameplay_field_force_ticks":0,
                "peak_reported_gameplay_force_n":0.,
            })
            old=positions.get(name)
            if state["source_digest"] != actor["source_digest"]:
                raise NativeAuditError("actor source asset changed during source audit")
            if old:
                old_position,old_velocity,old_energy,old_contact,origin=old
                state["path_distance_m"]+=math.dist(position,old_position)
                a=math.dist(velocity,old_velocity)*native["fps"]
                state["peak_estimated_acceleration_mps2"]=max(
                    state["peak_estimated_acceleration_mps2"],a)
                if a>acceleration_threshold_mps2:
                    anomalies.append({"frame":index,"actor_id":name,
                        "kind":"large_reported_velocity_step",
                        "metric":a,"unit":"estimated_mps2"})
                if count is not None and old_contact is not None and count!=old_contact:
                    state["contact_change_events"]+=1
                if (name in energy and old_energy is not None and
                    abs(energy[name]-old_energy)>energy_change_threshold_j):
                    anomalies.append({"frame":index,"actor_id":name,
                        "kind":"large_reported_kinetic_energy_delta",
                        "metric":abs(energy[name]-old_energy),"unit":"joule"})
            else:
                origin=position
            state["samples"]+=1
            state["max_reported_speed_mps"]=max(state["max_reported_speed_mps"],speed)
            state["max_height_m"]=max(state["max_height_m"],position[2])
            state["min_height_m"]=min(state["min_height_m"],position[2])
            state["net_displacement_m"]=math.dist(origin,position)
            state["positive_contact_ticks"]+=int(count is not None and count>0)
            game_force=game_field_forces.get(name,0.)
            state["positive_gameplay_field_force_ticks"]+=int(game_force>1e-6)
            state["peak_reported_gameplay_force_n"]=max(
                state["peak_reported_gameplay_force_n"],game_force)
            if name in energy:
                prior=state["peak_reported_kinetic_energy_j"]
                state["peak_reported_kinetic_energy_j"]=max(
                    prior if prior is not None else 0.,energy[name])
            positions[name]=(position,velocity,energy.get(name),count,origin)
        for row in transition["actors"]:
            if row["actor_id"] in results:
                results[row["actor_id"]]["chunk_migrations"]+=int(row["migrated"])
    if actor_id is not None and actor_id not in results:
        raise NativeAuditError("actor filter does not exist in selected source frames")
    for item in anomalies[:256]:
        results[item["actor_id"]]["event_count"]+=1
    report={
        "schema":"skeleton.game.native_diagnostics.v1",
        "authority":"read_only_verified_reported_game_physics_not_attestation",
        "track":journal.track,
        "source_gdd_digest":journal.gdd.source_digest,
        "start_frame":start_frame,"through_frame":last,
        "frames_scanned":last-start_frame+1,
        "full_prefix_replay_verified":prior_replay["verified_frames"],
        "actor_filter":actor_id,
        "anomaly_thresholds":{
            "estimated_acceleration_mps2":float(acceleration_threshold_mps2),
            "reported_energy_delta_j":float(energy_change_threshold_j),
        },
        "actor_metrics":[results[name] for name in sorted(results)],
        "events_truncated":len(anomalies)>256,
        "events":anomalies[:256],
        "source_observation_hash_chain":_digest(samples),
        "source_frame_evidence_chain":_digest(evidence),
        "verification":"reported_sample_and_CAS_replay_not_GPU_physics_attestation",
    }
    report["receipt_digest"]=_digest(report)
    return report
