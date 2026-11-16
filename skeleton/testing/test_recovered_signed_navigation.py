"""Actual signed geometry, route grounding, GPS and quest transition regressions."""
from dataclasses import replace
import hashlib
import hmac

import pytest

from skeleton.app.recovered_evidence import canonical,digest,EvidenceError
from skeleton.ai.game_builder.synthesized_quest_planner import plan_campaign
from skeleton.ai.game_builder.synthesized_quest_runtime import solution
from skeleton.ai.game_builder.grounded_quest_qualification import qualify_grounded_quest
from skeleton.frontier_nav.signed_navigation import route_body
from skeleton.frontier_nav.gps import FrameGPSHub,PositionFix,GPSRejected
from skeleton.frontier_nav.route_grounding import GroundingRejected

KEY=b"synthetic-route-approval-fixture-key"


def order():
    campaign={"schema":"skeleton.synthesized-quest.order.v1","campaign_id":"recovery",
              "title":"Lantern","seed":8,"length":3,
              "world":{"start":"dock","edges":{"dock":["hill"],"hill":["dock"]},"npcs":{}},
              "policy":{"banned_terms":[],"max_reward_per_step":4,"max_total_reward":12,
                        "allowed_reward_kinds":["xp"]},
              "mechanics":{"registry":[
                  {"id":"travel","provides":["travel"],"requires":[],"conflicts":[],"params":{}},
                  {"id":"quest","provides":["quest"],"requires":["travel"],"conflicts":[],"params":{}},
              ],"selected":["travel","quest"],"overrides":{}}}
    plan=plan_campaign(campaign,authorized=True)
    locations={"dock":[0,0,0],"hill":[10,0,0]}
    route={"route_id":"road","waypoints":["dock","hill"],"consumers":["quest"],
           "bidirectional":True,"note_id":"approved-road"}
    body=route_body(route,plan_digest=plan["digest"],geometry_digest=digest(locations))
    route["signature"]=hmac.new(KEY,route["note_id"].encode()+b"\n"+canonical(body),
                               hashlib.sha256).hexdigest()
    catalogue={"schema":"skeleton.signed-navigation.order.v1","plan_digest":plan["digest"],
               "coordinates":locations,"routes":[route]}
    return {"schema":"skeleton.grounded-quest.order.v1","campaign":campaign,"plan":plan,
            "expected_plan_digest":plan["digest"],"approval_catalogue":catalogue,
            "expected_approval_digest":digest(catalogue),"actions":solution(plan),
            "console":"local","era":"16bit","max_speed_per_frame":10,"expected_status":"completed"}


def resign_outer(value):
    value["expected_approval_digest"]=digest(value["approval_catalogue"])


def test_actual_signed_quest_navigation():
    value=order()
    report=qualify_grounded_quest(value,key=KEY,authorized=True)
    assert report["route_signature_verified"]
    assert report["navigation"]["snapshot"]["status"]=="completed"
    assert report["navigation"]["frame_count"]==len(value["actions"])+1
    assert not report["authoritative_engine_positions"]
    assert report==qualify_grounded_quest(value,key=KEY,authorized=True)


@pytest.mark.parametrize("change",["geometry","direction","consumer","route_id","waypoints"])
def test_signature_binds_exact_approved_route_even_with_new_catalogue_pin(change):
    value=order()
    route=value["approval_catalogue"]["routes"][0]
    if change=="geometry":
        value["approval_catalogue"]["coordinates"]["hill"][0]=11
    elif change=="direction":
        route["bidirectional"]=False
    elif change=="consumer":
        route["consumers"]=["dragon_map"]
    elif change=="route_id":
        route["route_id"]="other"
    else:
        route["waypoints"].reverse()
    resign_outer(value)
    with pytest.raises(GroundingRejected):
        qualify_grounded_quest(value,key=KEY,authorized=True)


def test_wrong_key_and_missing_consent():
    value=order()
    with pytest.raises(GroundingRejected):
        qualify_grounded_quest(value,key=b"x"*32,authorized=True)
    with pytest.raises(PermissionError):
        qualify_grounded_quest(value,key=KEY,authorized=False)


def test_speed_gate_cannot_be_bypassed_by_signed_route():
    value=order()
    value["max_speed_per_frame"]=1
    # Ensure the first action is a legal, signed move regardless of seed.
    value["actions"]=[{"op":"move","destination":"hill"}]
    value["expected_status"]="in_progress"
    with pytest.raises(GPSRejected):
        qualify_grounded_quest(value,key=KEY,authorized=True)


def test_gps_chain_binds_lane_hash_frame_and_length():
    hub=FrameGPSHub(frozenset({("local","era")}))
    updates=[hub.submit_frame("local","era",n,[PositionFix("actor",n,0)]) for n in range(3)]
    proofs=hub.proofs("local","era")
    assert FrameGPSHub.verify_chain(proofs,updates)
    assert not FrameGPSHub.verify_chain(proofs,updates[:-1])
    assert not FrameGPSHub.verify_chain((replace(proofs[0],console="other"),*proofs[1:]),updates)
    assert not FrameGPSHub.verify_chain(proofs,[replace(updates[0],proof_hash="a"*64),*updates[1:]])
    assert not FrameGPSHub.verify_chain(proofs,[replace(updates[0],frame=True),*updates[1:]])


def test_catalogue_pin_rejects_unreviewed_change():
    value=order()
    value["approval_catalogue"]["coordinates"]["hill"][0]=20
    with pytest.raises(EvidenceError):
        qualify_grounded_quest(value,key=KEY,authorized=True)
