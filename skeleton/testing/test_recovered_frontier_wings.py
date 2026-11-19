"""Canonical topology skin solver with three-axis flap/glide authored anchors."""
from copy import deepcopy
from dataclasses import replace
import math
import pytest
from skeleton.app.recovered_evidence import EvidenceError
from skeleton.app.frontier_wing_model import load_order,create_geometry
from skeleton.app.frontier_wing_motion import anchors,phase_weight
from skeleton.app.frontier_wing_replay import qualify_wings
from skeleton.jeeves.game_frontier_elastic_skin3d import simulate_elastic_skin,ElasticSkinError
from skeleton.jeeves.game_frontier_production import Vec3


def order():
    return {"schema":"skeleton.frontier-wing-replay.order.v1","fps":60,"subdivisions":4,
        "span_m":2,"chord_m":.8,"body_height_m":3,"frequency_hz":1.2,"amplitude_deg":35,
        "transition_frames":8,"checkpoint_stride":8,"maximum_step_m":.4,"strain_limit":.5,
        "phases":[{"mode":m,"frames":16,"wind":[0,1,0],"rain":rain,"temperature":20}
                  for m,rain in (("flap",0),("glide",20),("flap",0))],
        "material":{"mass":.08,"anchor_stiffness":40,"shear_stiffness":18,
                    "damping":2,"wind_drag":.12,"water_absorption":.2}}


def test_mesh_shared_seams_and_three_dimensional_motion():
    o=load_order(order())
    g=create_geometry(o)
    assert len(g.triangles)==4*o.subdivisions**2
    assert len(g.pins)<len(g.mesh.vertices)
    a=anchors(o,g,0,1)
    b=anchors(o,g,math.pi/2,1)
    assert a!=b
    assert max(p.z for p in b)>max(p.z for p in a)
    assert anchors(o,g,.1,0)==anchors(o,g,2.,0)


def test_transition_has_zero_endpoint_velocity():
    assert phase_weight(1,0,0,20)==1
    assert phase_weight(1,0,20,20)==0
    assert 1-phase_weight(1,0,.001,20)<1e-9
    assert phase_weight(1,0,19.999,20)<1e-9


def test_canonical_dynamic_skin_replay_and_glide():
    doc=order()
    before=deepcopy(doc)
    report=qualify_wings(doc,authorized=True)
    sim=report["simulation"]
    assert sim["frames"]==48 and report["source_frame_evaluations"]==96
    assert sim["metrics"]["glide_extended_frames"]==9
    assert sim["metrics"]["maximum_wetness"]>0
    assert sim["metrics"]["maximum_pin_error_m"]==0
    assert sim["metrics"]["minimum_triangle_area_m2"]>0
    assert report["native_frames_rendered"]==0
    assert doc==before


def test_explicit_anchors_reject_wrong_dimensions_and_floor_conflict():
    o=load_order(order())
    g=create_geometry(o)
    with pytest.raises(ElasticSkinError):
        simulate_elastic_skin(g.skeleton,g.mesh,g.clip,o.skin,time_ms=0,delta_s=.01,
                              anchor_positions=(Vec3(0,0,0),))
    points=list(anchors(o,g,0,0))
    points[g.pins[0]]=Vec3(0,0,-1)
    with pytest.raises(ElasticSkinError,match="floor"):
        simulate_elastic_skin(g.skeleton,g.mesh,g.clip,o.skin,time_ms=0,delta_s=.01,
                              pinned_vertices=g.pins,anchor_positions=tuple(points))


def test_budget_and_permission():
    with pytest.raises(PermissionError):
        qualify_wings({},authorized=False)
    doc=order()
    doc["phases"][0]["frames"]=10000
    with pytest.raises(EvidenceError):
        load_order(doc)


def test_rain_changes_actual_skin_state():
    doc=order()
    dry=deepcopy(doc)
    dry["phases"][1]["rain"]=0
    a=qualify_wings(doc,authorized=True)["simulation"]
    b=qualify_wings(dry,authorized=True)["simulation"]
    assert a["head"]!=b["head"]
    assert a["metrics"]["maximum_wetness"]>b["metrics"]["maximum_wetness"]
