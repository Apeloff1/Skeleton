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
