"""Source-replayed comparison of two native Godot physics sessions.

Compare cross-FPS runs on exact rational-aligned fixed-step times, no floating
time matching or fake interpolation. Reports per-actor position/velocity and
contact divergence with immutable source provenance. Different simulation FPS
need not yield identical trajectories; a tolerance finding is not a claim
about engine speed or a failure to attain rendered FPS.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game_frontier_receipt_journal import FrameReceiptJournal


class NativeComparisonError(ValueError):
    pass


def _digest(data: object) -> str:
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def compare_native_sessions(
    left: FrameReceiptJournal, right: FrameReceiptJournal, *,
    actor_id: str | None = None,
    max_aligned_frames: int = 1024,
    tolerance_m: float = .5,
) -> dict:
    """Validate *both* retained source chains before exact rational comparison.

    Comparisons do not resample between engine ticks: time i/FPS_L must equal
    j/FPS_R exactly. Early frames with no second overlap are rejected.
    """
    from .game_frontier_receipt_journal import FrameReceiptJournal
    if (not isinstance(left,FrameReceiptJournal) or
        not isinstance(right,FrameReceiptJournal) or
        actor_id is not None and (
            type(actor_id) is not str or not 1<=len(actor_id)<=128) or
        type(max_aligned_frames) is not int or not 2<=max_aligned_frames<=4096 or
        type(tolerance_m) not in (int,float) or not math.isfinite(tolerance_m) or
        not .000001<=tolerance_m<=100000):
        raise NativeComparisonError("bounded typed cross-session comparison required")
    if left.gdd.source_digest != right.gdd.source_digest:
        raise NativeComparisonError("cannot compare different signed GDD canons")
    ls,rs=left.stats(),right.stats()
    lf,rf=ls["fps"],rs["fps"]
    if lf not in (30,50,60,120) or rf not in (30,50,60,120):
        raise NativeComparisonError("two valid fixed-tick native sessions required")
    if ls["head"]<1 or rs["head"]<1:
        raise NativeComparisonError("at least two committed samples per session required")
    if left is right and left.track==right.track:
        raise NativeComparisonError("select two distinct game session tracks")
    # Any bad predecessor prevents certification even if comparison window
    # would omit the corrupt frame.
    lr=left.replay()
    rr=right.replay()
    l0,r0=left.native_sample(0),right.native_sample(0)
    if l0 is None or r0 is None:
        raise NativeComparisonError("native session telemetry missing")
    source_l={a["id"]:a["source_digest"] for a in l0["actors"]}
    source_r={a["id"]:a["source_digest"] for a in r0["actors"]}
    if not source_l or source_l!=source_r:
        raise NativeComparisonError("cross-session source actor catalog disagrees")
    if actor_id is not None and actor_id not in source_l:
        raise NativeComparisonError("selected actor not in native source catalog")
    from .game_frontier_native_fields import inspect_native_force_fields
    first_left=inspect_native_force_fields(l0)
    first_right=inspect_native_force_fields(r0)
    if bool(first_left)!=bool(first_right) or (
        first_left is not None and
        l0["native_force_fields"]!=r0["native_force_fields"]):
        raise NativeComparisonError("cross-FPS source game force fields differ")
    chosen=[actor_id] if actor_id is not None else sorted(source_l)
    sums={name:{"id":name,"source_digest":source_l[name],
                "matched_ticks":0,"position_squared_error_sum":0.,
                "maximum_position_delta_m":0.,"maximum_velocity_delta_mps":0.,
                "different_reported_contact_ticks":0,
                "maximum_reported_kinetic_energy_delta_j":None,
                "maximum_reported_gameplay_force_delta_n":None,
                "different_active_gameplay_force_ticks":0,
                "position_drift_tolerance_exceedances":0} for name in chosen}
    paired=[]
    evidence=[]
    # Time i/lf == j/rf; indices must match exactly via integers.
    for i in range(ls["head"]+1):
        numerator=i*rf
        if numerator%lf:
            continue
        j=numerator//lf
        if j>rs["head"] or len(paired)>=max_aligned_frames:
            break
        a,b=left.native_sample(i),right.native_sample(j)
        if a is None or b is None:
            raise NativeComparisonError("missing synchronized native source frame")
        if a.get("signed_gdd_digest")!=b.get("signed_gdd_digest"):
            raise NativeComparisonError("signed scene identity changed between sessions")
        left_items={item["id"]:item for item in a["actors"]}
        right_items={item["id"]:item for item in b["actors"]}
        if ({k:v["source_digest"] for k,v in left_items.items()}!=source_l or
            {k:v["source_digest"] for k,v in right_items.items()}!=source_r):
            raise NativeComparisonError("source identity drift within compared game")
        field_l=inspect_native_force_fields(a)
        field_r=inspect_native_force_fields(b)
        if bool(field_l)!=bool(field_r) or (
            field_l is not None and
            a["native_force_fields"]!=b["native_force_fields"]):
            raise NativeComparisonError("native gameplay field source drift across FPS")
        def actor_field_magnitudes(source):
            result={}
            for item in source.get("previous_step_field_forces",()):
                strength=math.dist([0.,0.,0.],item["force_world_xyz_n"])
                key=item["actor_id"]
                result[key]=result.get(key,0.)+strength
            return result
        force_l=actor_field_magnitudes(a) if field_l else {}
        force_r=actor_field_magnitudes(b) if field_r else {}
        la=left.native_dynamics_evidence(i)
        ra=right.native_dynamics_evidence(j)
        if bool(la) != bool(ra):
            raise NativeComparisonError("dynamics schema downgraded between sessions")
        ea={q["id"]:q["kinetic_energy_j"] for q in la["actors"]} if la else {}
        eb={q["id"]:q["kinetic_energy_j"] for q in ra["actors"]} if ra else {}
        for name in chosen:
            p,q=left_items[name],right_items[name]
            pos_delta=math.dist(p["world_xyz_m"],q["world_xyz_m"])
            vel_delta=math.dist(p["velocity_xyz_mps"],q["velocity_xyz_mps"])
            row=sums[name]
            row["matched_ticks"]+=1
            row["position_squared_error_sum"]+=pos_delta*pos_delta
            row["maximum_position_delta_m"]=max(row["maximum_position_delta_m"],pos_delta)
            row["maximum_velocity_delta_mps"]=max(
                row["maximum_velocity_delta_mps"],vel_delta)
            row["different_reported_contact_ticks"]+=int(
                p.get("contact_count")!=q.get("contact_count"))
            row["position_drift_tolerance_exceedances"]+=int(pos_delta>tolerance_m)
            if field_l:
                l_force=force_l.get(name,0.)
                r_force=force_r.get(name,0.)
                existing=row["maximum_reported_gameplay_force_delta_n"]
                row["maximum_reported_gameplay_force_delta_n"]=max(
                    existing if existing is not None else 0.,abs(l_force-r_force))
                row["different_active_gameplay_force_ticks"]+=int(
                    (l_force>1e-6)!=(r_force>1e-6))
            if la:
                energy_delta=abs(ea[name]-eb[name])
                existing=row["maximum_reported_kinetic_energy_delta_j"]
                row["maximum_reported_kinetic_energy_delta_j"]=max(
                    existing if existing is not None else 0.,energy_delta)
        paired.append({"left_tick":i,"right_tick":j,
                       "relative_time_s":i/lf})
        evidence.append((left.load(i)[0].receipt_digest,
                         right.load(j)[0].receipt_digest,
                         left.native_chunk_evidence(i)["receipt_digest"],
                         right.native_chunk_evidence(j)["receipt_digest"]))
    if len(paired)<2:
        raise NativeComparisonError("insufficient exact shared native physics ticks")
    metrics=[]
    for name in chosen:
        row=sums[name]
        row["rms_position_delta_m"]=math.sqrt(
            row.pop("position_squared_error_sum")/row["matched_ticks"])
        metrics.append(row)
    output={
        "schema":"skeleton.game.native_session_comparison.v1",
        "authority":"source_replayed_reported_native_physics_not_equivalent_rendered_FPS",
        "signed_gdd_digest":left.gdd.source_digest,
        "left":{"track":left.track,"fps":lf,
                "verified_frames":lr["verified_frames"],
                "source_scene_candidate_digest":l0["scene_candidate_digest"]},
        "right":{"track":right.track,"fps":rf,
                 "verified_frames":rr["verified_frames"],
                 "source_scene_candidate_digest":r0["scene_candidate_digest"]},
        "actor_filter":actor_id,
        "position_tolerance_m":float(tolerance_m),
        "shared_fixed_ticks":paired,
        "aligned_pairs_compared":len(paired),
        "actor_metrics":metrics,
        "all_actor_positions_within_tolerance":all(
            row["position_drift_tolerance_exceedances"]==0 for row in metrics),
        "replayed_pair_evidence_digest":_digest(evidence),
        "verification":"exact_rational_tick_source_comparison_not_visual_or_GPU_attestation",
    }
    output["receipt_digest"]=_digest(output)
    return output
