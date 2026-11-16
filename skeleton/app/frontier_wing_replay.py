"""Run actual canonical elastic skin integration over continuous 3D wing anchors."""
from __future__ import annotations
from dataclasses import asdict
import math
from skeleton.app.recovered_evidence import EvidenceError,digest,seal
from skeleton.app.frontier_wing_model import load_order,create_geometry
from skeleton.app.frontier_wing_motion import anchors,phase_weight
from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_elastic_skin3d import ElasticSkinState,simulate_elastic_skin

GENESIS="0"*64


def length(v):
    return math.sqrt(v.dot(v))


def simulate(document, *, frame_sink=None):
    order=load_order(document)
    geometry=create_geometry(order)
    clock=PresentationClock(order.fps)
    weight=1. if order.phases[0].mode=="flap" else 0.
    phase=0.
    initial=anchors(order,geometry,phase,weight)
    previous=initial
    state=ElasticSkinState(initial,tuple(v.scaled(0) for v in initial))
    head=GENESIS
    checkpoints=[]
    failures={"excess_strain":0,"excess_frame_displacement":0,"degenerate_triangles":0,
              "floor_penetration":0,"pin_mismatch":0}
    metrics={"maximum_strain":0.,"maximum_frame_displacement_m":0.,"maximum_pin_error_m":0.,
             "minimum_triangle_area_m2":None,"maximum_wetness":0.,"glide_extended_frames":0,
             "flap_frames":0,"maximum_left_right_tip_height_m":0.}
    frame_index=0
    for block in order.phases:
        start_weight=weight
        target=1. if block.mode=="flap" else 0.
        for local in range(block.frames):
            tick=clock.next_frame()
            dt=(clock.deadline(tick.frame_index+1)-tick.deadline_ns)/1e9
            phase=(phase+2*math.pi*order.frequency*dt)%(2*math.pi)
            weight=phase_weight(start_weight,target,local+1,order.transition_frames)
            posed=anchors(order,geometry,phase,weight)
            frame=simulate_elastic_skin(geometry.skeleton,geometry.mesh,geometry.clip,order.skin,
                time_ms=tick.deadline_ns//1_000_000,delta_s=dt,wind_mps=block.wind,
                rainfall_mm_h=block.rain,air_temperature_c=block.temperature,
                pinned_vertices=geometry.pins,state=state,anchor_positions=posed)
            pins=max(length(frame.positions[i]-posed[i]) for i in geometry.pins)
            move=max(length(p-q) for p,q in zip(frame.positions,previous,strict=True))
            areas=[length((frame.positions[b]-frame.positions[a]).cross(
                          frame.positions[c]-frame.positions[a]))*.5
                   for a,b,c in geometry.triangles]
            min_area=min(areas)
            failures["excess_strain"]+=frame.max_measured_strain>order.strain_limit+1e-5
            failures["excess_frame_displacement"]+=move>order.maximum_step_m
            failures["degenerate_triangles"]+=min_area<=1e-10
            failures["floor_penetration"]+=any(p.z< -1e-9 for p in frame.positions)
            failures["pin_mismatch"]+=pins>1e-9
            metrics["maximum_strain"]=max(metrics["maximum_strain"],frame.max_measured_strain)
            metrics["maximum_frame_displacement_m"]=max(metrics["maximum_frame_displacement_m"],move)
            metrics["maximum_pin_error_m"]=max(metrics["maximum_pin_error_m"],pins)
            metrics["maximum_wetness"]=max(metrics["maximum_wetness"],frame.wetness)
            metrics["minimum_triangle_area_m2"]=min_area if metrics["minimum_triangle_area_m2"] is None else min(min_area,metrics["minimum_triangle_area_m2"])
            if block.mode=="glide" and weight==0:
                metrics["glide_extended_frames"]+=1
            if block.mode=="flap" and weight==1:
                metrics["flap_frames"]+=1
            metrics["maximum_left_right_tip_height_m"]=max(metrics["maximum_left_right_tip_height_m"],
                max(p.z for p in frame.positions)-min(p.z for p in frame.positions))
            record={"frame":frame_index,"deadline_ns":tick.deadline_ns,"mode":block.mode,
                    "amplitude_weight":weight,"phase":phase,"skin_receipt":frame.evidence_digest,
                    "strain":frame.max_measured_strain,"pin_error":pins,"max_displacement":move,
                    "min_area":min_area}
            head=digest({"previous":head,"record":record})
            if frame_sink is not None:
                # Immutable tuples and detached evidence; downstream consumers
                # cannot mutate the canonical simulation state.
                frame_sink(frame_index,tick.deadline_ns,frame.positions,head)
            state=ElasticSkinState(frame.positions,frame.velocities,frame.wetness,frame.temperature_c)
            previous=frame.positions
            frame_index+=1
            if frame_index%order.checkpoint_stride==0 or frame_index==order.frames:
                checkpoints.append({"frames":frame_index,"head":head,"record":record,
                     "state_digest":digest({"positions":[asdict(p) for p in state.positions],
                         "velocities":[asdict(v) for v in state.velocities],
                         "wetness":state.wetness,"temperature":state.temperature_c})})
    if frame_index!=order.frames:
        raise EvidenceError("canonical frame accounting mismatch")
    return {"frames":frame_index,"head":head,"mesh_digest":geometry.mesh.digest,
            "vertices":len(geometry.mesh.vertices),"triangles":len(geometry.triangles),
            "pinned_vertices":len(geometry.pins),"checkpoints":checkpoints,
            "metrics":metrics,"invariant_failure_frames":failures,
            "reference_invariants_passed":not any(failures.values())}


def qualify_wings(document,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit membrane simulation operator required")
    first=simulate(document)
    second=simulate(document)
    if first!=second:
        raise EvidenceError("wing membrane deterministic replay diverged")
    return seal({"schema":"skeleton.frontier-wing-replay.report.v1","order_digest":digest(document),
                 "simulation":first,"source_frame_evaluations":first["frames"]*2,
                 "independent_source_replay_matched":True,"native_frames_rendered":0,
                 "physical_aerodynamics_validated":False,"native_fem_executed":False,
                 "visual_quality_certified":False,"release_certified":False})
