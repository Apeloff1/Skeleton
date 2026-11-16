"""Quest execution using signed route geometry and canonical navigation receipts."""
from __future__ import annotations

from dataclasses import asdict

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, identifier, integer, digest, seal,
)
from skeleton.ai.game_builder.synthesized_quest_runtime import Campaign
from skeleton.frontier_nav.signed_navigation import load_approvals
from skeleton.frontier_nav.gps import FrameGPSHub,PositionFix

MAX_ACTIONS=512


def _fix(nav,location):
    x,y,z=nav.locations[location]
    return PositionFix("quest-player",x,y,z,0.0,location)


def _execute(order,nav,actions):
    run=Campaign.start(order["campaign"],order["plan"],
                       expected_plan_digest=order["expected_plan_digest"],authorized=True)
    lane=(identifier(order["console"]),identifier(order["era"]))
    max_speed=integer(order["max_speed_per_frame"],1,3_000_000_000)
    hub=FrameGPSHub(frozenset({lane}),max_speed_per_frame=max_speed)
    seen=[]
    unsubscribe=hub.subscribe(seen.append)
    receipts=[]
    try:
        hub.submit_frame(*lane,0,[_fix(nav,run.location)])
        for index,action in enumerate(actions,1):
            old=run.location
            route=None
            if type(action) is dict and action.get("op")=="move":
                fields(action,{"op","destination"})
                route=nav.grounder.ground("quest",(old,identifier(action["destination"])))
            run.apply(action)
            if run.location!=old and route is None:
                raise EvidenceError("movement without signed route witness")
            update=hub.submit_frame(*lane,index,[_fix(nav,run.location)])
            receipts.append({"frame":index,"action_digest":digest(action),
                             "location":run.location,"navigation_hash":update.proof_hash,
                             "route_ids":[] if route is None else list(route.route_ids),
                             "note_ids":[] if route is None else list(route.note_ids)})
    finally:
        unsubscribe()
    proofs=hub.proofs(*lane)
    if len(proofs)!=len(actions)+1 or len(seen)!=len(proofs) or not FrameGPSHub.verify_chain(proofs,seen):
        raise EvidenceError("canonical navigation receipt chain differs")
    if hub.position(*lane,"quest-player")!=_fix(nav,run.location):
        raise EvidenceError("navigation position disagrees with campaign")
    snapshot=run.snapshot()
    return {"snapshot":snapshot,"navigation_head":proofs[-1].digest,
            "navigation_proof_digest":digest([asdict(row) for row in proofs]),
            "receipts":receipts,"frame_count":len(proofs)}


def qualify_grounded_quest(order,*,key,authorized):
    if authorized is not True:
        raise PermissionError("explicit signed-navigation operator required")
    fields(order,{"schema","campaign","plan","expected_plan_digest","approval_catalogue",
                  "expected_approval_digest","actions","console","era","max_speed_per_frame",
                  "expected_status"})
    if order["schema"]!="skeleton.grounded-quest.order.v1":
        raise EvidenceError("unsupported grounded quest order")
    if order["expected_status"] not in ("completed","failed","in_progress"):
        raise EvidenceError("unknown canonical quest status")
    actions=array(order["actions"],1,MAX_ACTIONS)
    seed=Campaign.start(order["campaign"],order["plan"],
                        expected_plan_digest=order["expected_plan_digest"],authorized=True)
    nav=load_approvals(order["approval_catalogue"],world=seed.order.world,
                       plan_digest=order["expected_plan_digest"],
                       expected_digest=order["expected_approval_digest"],key=key)
    first=_execute(order,nav,actions)
    second=_execute(order,nav,actions)
    if first!=second or first["snapshot"]["status"]!=order["expected_status"]:
        raise EvidenceError("grounded quest replay or requested status differs")
    snapshot=first["snapshot"]
    restored=Campaign.restore(order["campaign"],order["plan"],snapshot,
                              expected_plan_digest=order["expected_plan_digest"],
                              expected_save_digest=snapshot["digest"],authorized=True)
    if restored.snapshot()!=snapshot:
        raise EvidenceError("canonical quest reconstruction differs")
    return seal({"schema":"skeleton.grounded-quest.qualification.v1","order_digest":digest(order),
                 "plan_digest":order["expected_plan_digest"],"approval_digest":nav.approval_digest,
                 "geometry_digest":nav.geometry_digest,"signed_routes_verified":nav.routes,
                 "navigation":first,"replay_matched":True,"route_signature_verified":True,
                 "authoritative_engine_positions":False,"supplied_geometry_only":True,
                 "native_engine_executed":False,"release_certified":False})
