import pytest
from skeleton.ai.workflow_ir import WorkflowIR,WorkflowNode,WorkflowEdge
def n(i,**kw):return WorkflowNode(i,"cap:"+i,**kw)
def test_roundtrip_identity_is_order_independent():
 a=WorkflowIR("w",(n("a"),n("b")),(WorkflowEdge("a","b"),))
 b=WorkflowIR("w",(n("b"),n("a")),(WorkflowEdge("a","b"),))
 assert a.digest==b.digest and a.payload()==b.payload()
def test_cycle_and_missing_node_fail_closed():
 with pytest.raises(ValueError):WorkflowIR("w",(n("a"),n("b")),(WorkflowEdge("a","b"),WorkflowEdge("b","a")))
 with pytest.raises(ValueError):WorkflowIR("w",(n("a"),),(WorkflowEdge("a","x"),))
def test_authority_retry_timeout_are_explicit():
 x=n("a",authority="worker:bounded",retries=2,timeout_seconds=10,compensation="undo")
 assert x.authority=="worker:bounded" and x.compensation=="undo"
def test_invalid_runtime_controls_fail_closed():
 with pytest.raises(ValueError):n("a",retries=-1)
 with pytest.raises(ValueError):n("a",timeout_seconds=0)
