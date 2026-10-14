from __future__ import annotations
import pytest
from skeleton.automation.build_order import *
def test_hard_dependency_blocks_downstream_maturity():
 o=BuildOrder(("AIQ.1","AIQ.2"),(BuildDependency("AIQ.1","AIQ.2",DependencyKind.HARD),));assert not o.maturity_allowed("AIQ.2",()) and o.maturity_allowed("AIQ.2",("AIQ.1",))
def test_soft_overlap_does_not_serialize_parallel_work():
 o=BuildOrder(("AIQ.1","AIQ.2"),(BuildDependency("AIQ.1","AIQ.2",DependencyKind.SOFT),));assert o.ready(())==("AIQ.1","AIQ.2")
def test_active_stop_blocks_with_explanation():
 o=BuildOrder(("AIQ.1",),stops=(BuildStopCondition("AIQ.1","STOP.RISK",True,"unresolved-risk"),));assert o.blocked_reasons("AIQ.1",())==("stop:STOP.RISK:unresolved-risk",)
def test_hard_cycle_rejected():
 with pytest.raises(BuildOrderError,match="cycle"):BuildOrder(("AIQ.1","AIQ.2"),(BuildDependency("AIQ.1","AIQ.2",DependencyKind.HARD),BuildDependency("AIQ.2","AIQ.1",DependencyKind.HARD)))
def test_dangling_dependency_rejected():
 with pytest.raises(BuildOrderError,match="dangling"):BuildOrder(("AIQ.1",),(BuildDependency("AIQ.9","AIQ.1",DependencyKind.HARD),))
def test_order_recomputes_when_completed_set_changes():
 o=BuildOrder(("AIQ.1","AIQ.2"),(BuildDependency("AIQ.1","AIQ.2",DependencyKind.HARD),));assert o.ready(())==("AIQ.1",);assert o.ready(("AIQ.1",))==("AIQ.2",)

def test_dependency_kind_and_stop_state_are_runtime_typed():
 with pytest.raises(BuildOrderError,match="DependencyKind"):BuildDependency("AIQ.1","AIQ.2","hard")
 with pytest.raises(BuildOrderError,match="active must be bool"):BuildStopCondition("AIQ.1","STOP.X",1,"risk")
def test_unknown_and_duplicate_completion_state_rejected():
 o=BuildOrder(("AIQ.1","AIQ.2"))
 with pytest.raises(BuildOrderError,match="unknown node"):o.ready(("AIQ.9",))
 with pytest.raises(BuildOrderError,match="duplicate completed"):o.ready(("AIQ.1","AIQ.1"))
def test_duplicate_topology_identity_rejected():
 with pytest.raises(BuildOrderError,match="duplicate node"):BuildOrder(("AIQ.1","AIQ.1"))
 d=BuildDependency("AIQ.1","AIQ.2",DependencyKind.HARD)
 with pytest.raises(BuildOrderError,match="duplicate dependency"):BuildOrder(("AIQ.1","AIQ.2"),(d,d))
def test_snapshot_recomputes_blocked_state_deterministically():
 o=BuildOrder(("AIQ.1","AIQ.2"),(BuildDependency("AIQ.1","AIQ.2",DependencyKind.HARD),))
 before=o.snapshot(());after=o.snapshot(("AIQ.1",))
 assert before==( ("AIQ.1",False,()),("AIQ.2",False,("dependency:AIQ.1",)) )
 assert after==( ("AIQ.1",True,()),("AIQ.2",False,()) )
def test_completed_node_cannot_be_promoted_again():
 o=BuildOrder(("AIQ.1",))
 with pytest.raises(BuildOrderError,match="completed node"):o.maturity_allowed("AIQ.1",("AIQ.1",))
