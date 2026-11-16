"""Coupled actual production candidate source owners, not GPU/render evidence."""
from copy import deepcopy

import pytest

from skeleton.app.frontier_environment_model import load_order
from skeleton.app.frontier_environment_replay import qualify_environment
from skeleton.app.recovered_evidence import EvidenceError


def block(frames=12,rain=0,fog=0,temp=10,wind=None):
    return {"frames":frames,"wind":wind or [1,0,0],"temperature":temp,"humidity":.7,
            "rain":rain,"sunlight":.5,"altitude":0,"fog":fog,"cloud":0,
            "acceleration":[0,0,0],"velocity":[0,0,0]}


def order():
    return {"schema":"skeleton.frontier-environment-replay.order.v1","fps":60,
            "checkpoint_stride":4,"area_samples":2,"ground":0,"sun":[0,0,1],
            "microclimate":{"temperature":10,"soil_water":.1,"ice":0,"sediment":0,
                            "roughness":.2,"vegetation":.5,"pressure_gradient":[0,0,0],"heat_flux":0},
            "traction":{"normal":[0,0,1],"static_friction":.8,"dynamic_friction":.6,"foothold":.1},
            "segments":[{"id":"body","kg":20,"location":[0,0,1],"radius":.3,"carried":False}],
            "feet":[{"id":f"foot{i}","position":[x,y,0],"capacity":200,"friction":.7}
                    for i,(x,y) in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)])],
            "shrubs":[{"id":"bush","root":[3,0,0],"tip":[3,0,2],"stiffness":4,"mass":1,"radius":.1}],
            "rocks":[{"id":"rock","position":[4,0,.3],"radius":.3,"mass":1}],
            "leaves":[{"id":"leaf","shrub":"bush","anchor":[3,0,2],"center":[3,0,2],
                       "normal":[0,0,1],"width":.2,"length":.4,"opacity":.8,"mass":.05,"stiffness":4}],
            "surfaces":[{"id":"ground","position":[3,0,0],"normal":[0,0,1],
                         "albedo":[.7,.7,.7],"roughness":.5}],
            "lights":[{"id":"sunlamp","position":[3,0,10],"intensity":100,"radius":.1,"color":[1,1,1]}],
            "occluders":[],"weather":[block()],"contacts":[]}


def test_coupled_reference_runs_exact_frames_and_replays():
    value=order()
    original=deepcopy(value)
    result=qualify_environment(value,authorized=True)
    assert result["simulation"]["frames"]==12
    counts=result["simulation"]["counts"]
    assert counts["leaf_shadow_checks"]==12 and counts["surface_samples"]==12
    assert len(result["simulation"]["checkpoint_receipts"])==3
    assert result["source_frames_executed"]==24
    assert result["independent_source_replay_matched"]
    assert result["host_engine_frames_rendered"]==0
    assert not result["gpu_raytracing_executed"]
    assert value==original


def test_weather_changes_real_climate_and_light_transport():
    a=qualify_environment(order(),authorized=True)["simulation"]
    value=order()
    value["weather"]=[block(rain=600,fog=.5,temp=-10)]
    b=qualify_environment(value,authorized=True)["simulation"]
    assert b["head"]!=a["head"]
    assert b["extrema"]["max_ice"]>a["extrema"]["max_ice"]
    assert b["extrema"]["min_volumetric_transmission"]<a["extrema"]["min_volumetric_transmission"]


def test_contact_changes_moving_geometry_chain():
    a=qualify_environment(order(),authorized=True)["simulation"]
    value=order()
    value["contacts"]=[{"frame":1,"position":[3,0,2],"impulse":[.1,0,0],"radius":.2}]
    b=qualify_environment(value,authorized=True)["simulation"]
    assert b["counts"]["contact_hits"]>=1
    assert b["head"]!=a["head"]
    assert b["extrema"]["max_leaf_displacement_m"]>0


def test_disabled_qualification_and_work_ceilings():
    with pytest.raises(PermissionError):
        qualify_environment({},authorized=False)
    value=order()
    value["weather"]=[block(frames=10000),block(frames=1)]
    with pytest.raises(EvidenceError):
        load_order(value)
    value=order()
    value["leaves"][0]["shrub"]="unregistered"
    with pytest.raises(EvidenceError):
        load_order(value)


def test_duplicate_identity_and_invalid_geometry_rejected():
    value=order()
    value["rocks"][0]["id"]="leaf"
    with pytest.raises(EvidenceError):
        load_order(value)
    value=order()
    value["sun"]=[0,0,-1]
    with pytest.raises(EvidenceError):
        load_order(value)


def test_balance_uses_current_weather_reduced_grip():
    value=order()
    value["weather"][0]["acceleration"]=[30,0,0]
    result=qualify_environment(value,authorized=True)["simulation"]
    assert result["counts"]["unstable_balance_frames"]==12
    assert result["extrema"]["min_balance_margin_m"]<0
