"""Seven-plane original game delivery assurance with explicit unresolved gaps.

Coverage is reproducibly calculated from actual source receipts; no "100%"
score can override missing native observations, legal clearance, months of
uptime, or external model-weight attestations. Publication is fail-closed.
"""
from __future__ import annotations
from typing import Mapping
from .game_frontier_expedition import ExpeditionError,_digest

SCHEMA="skeleton.game.seven_plane_release_assurance.v1"
AXES=("rig","society","performance","dragon_vision","controller_latency",
      "production_watchdog","rights_and_native")
_REQUIRED_KEYS={
    "rig":("rig_digest","soft_body_receipt"),
    "society":("snapshot_digest","world"),
    "performance":("receipt_digest","story_digest"),
    "dragon_vision":("receipt_digest","frame_count"),
    "controller_latency":("receipt_digest","observed_events"),
    "production_watchdog":("snapshot_digest","world"),
    "rights_and_native":("rights_signed","native_game_executed",
                         "physical_controller_verified","long_duration_days"),
}

def objectively_review_seven_planes(world_digest:str,artifacts:Mapping, *,
                                     reference_manifest:Mapping|None=None)->dict:
    if (not isinstance(world_digest,str) or len(world_digest)!=64
            or not isinstance(artifacts,Mapping) or set(artifacts)!=set(AXES)):
        raise ExpeditionError("original game assurance requires all seven independent planes")
    reviews=[]
    for axis in AXES:
        data=artifacts[axis]
        if not isinstance(data,Mapping):
            raise ExpeditionError("game assurance axis lacks source evidence")
        needed=_REQUIRED_KEYS[axis]
        if any(key not in data for key in needed):
            raise ExpeditionError("game assurance evidence axis incomplete: "+axis)
        if axis=="rights_and_native":
            approved=(
                data["rights_signed"] is True and
                data["native_game_executed"] is True and
                data["physical_controller_verified"] is True and
                type(data["long_duration_days"]) is int and
                data["long_duration_days"]>=30
            )
            required_missing=[
                key for key in needed if (
                    data[key] is not True if key!="long_duration_days"
                    else type(data[key]) is not int or data[key]<30
                )
            ]
        else:
            approved=True
            required_missing=[]
            for key in needed:
                value=data[key]
                if value is None or value=="" or value==0:
                    required_missing.append(key)
                    approved=False
            if data.get("world",data.get("world_digest",world_digest))!=world_digest:
                raise ExpeditionError("game assurance mixes different world sources")
        row={
            "axis":axis,"checked_source_digest":_digest(dict(data)),
            "source":world_digest,"evidence_fields":list(needed),
            "present":len(needed)-len(required_missing),
            "missing":required_missing,"passed":approved,
            "verified_external_authority":False,
        }
        row["receipt_digest"]=_digest(row)
        reviews.append(row)
    if reference_manifest is not None:
        if not isinstance(reference_manifest,Mapping) or reference_manifest.get("world_digest")!=world_digest:
            raise ExpeditionError("assurance reference belongs to a foreign authored campaign")
    pass_count=sum(row["passed"] for row in reviews)
    missing=[row["axis"]+"."+key for row in reviews for key in row["missing"]]
    approved=pass_count==len(AXES) and not missing
    result={
        "schema":SCHEMA,"world":world_digest,
        "axes":reviews,"passed":pass_count,"total":len(AXES),
        "coverage_pct":round(100*pass_count/len(AXES),2),
        "unresolved_gaps":missing,"source_checks_completed":True,
        "production_release_approved":False,
        "publication_authorized":False,
        "requested_external_approvals_validated":False,
        "all_required_artifacts_present":approved,
        "source_bound_only":True,
    }
    result["receipt_digest"]=_digest(result)
    return result

def verify_seven_planes(world_digest:str,artifacts:Mapping,report:dict)->None:
    if not isinstance(report,dict) or report!=objectively_review_seven_planes(world_digest,artifacts):
        raise ExpeditionError("seven-plane assurance differs from actual game artifact source")
