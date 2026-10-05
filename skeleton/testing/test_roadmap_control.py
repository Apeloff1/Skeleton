from __future__ import annotations
import hashlib,pytest
from skeleton.automation.roadmap_control import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def item(i="ROAD.1",**kw):
 v=dict(work_package_id="WP.1",build_node_id="AIQ.1",risk_ids=("RISK.1",),acceptance_gate_ids=("GATE.1",));v.update(kw);return RoadmapItem(i,**v)
def test_item_links_work_build_risk_and_acceptance_gate():assert item().build_node_id=="AIQ.1"
def test_breadth_freeze_requires_architecture_decision():
 with pytest.raises(RoadmapError,match="architecture decision"):item(top_level_scope=True)
 assert item(top_level_scope=True,architecture_decision_id="ADR.118").architecture_decision_id=="ADR.118"
def test_dependency_cycle_and_unknown_edges_fail_closed():
 with pytest.raises(RoadmapError,match="cycle"):RoadmapControl((item("ROAD.1"),item("ROAD.2")),(RoadmapDependency("ROAD.1","ROAD.2"),RoadmapDependency("ROAD.2","ROAD.1")))
 with pytest.raises(RoadmapError,match="unknown roadmap dependency"):RoadmapControl((item(),),(RoadmapDependency("ROAD.1","ROAD.9"),))
def test_revision_lineage_requires_existing_parent_and_rationale():
 r=RoadmapControl((item(),))
 with pytest.raises(RoadmapError,match="unknown revision parent"):r.add_revision(RoadmapRevision("REV.2","REV.1",S("a"),"replan",("ROAD.1",)))
 r.add_revision(RoadmapRevision("REV.1",None,S("a"),"initial",("ROAD.1",)))
 assert r.add_revision(RoadmapRevision("REV.2","REV.1",S("b"),"assumption changed",("ROAD.1",))).parent_revision_id=="REV.1"
def test_revision_cannot_reference_hidden_scope():
 r=RoadmapControl((item(),))
 with pytest.raises(RoadmapError,match="unknown item"):r.add_revision(RoadmapRevision("REV.1",None,S("a"),"initial",("ROAD.9",)))
