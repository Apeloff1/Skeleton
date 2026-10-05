from __future__ import annotations
import pytest
from skeleton.automation.traceability import *
def matrix():
 ns=(TraceNode("REQ.1",NodeKind.REQUIREMENT,"plan:1"),TraceNode("IMPL.1",NodeKind.IMPLEMENTATION,"a.py"),TraceNode("TEST.1",NodeKind.TEST,"test_a.py"),TraceNode("EVID.1",NodeKind.EVIDENCE,"receipt:1"))
 es=(TraceEdge("IMPL.1","REQ.1",EdgeKind.IMPLEMENTS),TraceEdge("TEST.1","IMPL.1",EdgeKind.VERIFIES),TraceEdge("EVID.1","TEST.1",EdgeKind.EVIDENCES));return TraceabilityMatrix(ns,es)
def test_bidirectional_impact_from_requirement_reaches_evidence():assert matrix().impact("REQ.1")==("EVID.1","IMPL.1","REQ.1","TEST.1")
def test_changed_implementation_reaches_requirement_and_verification():assert set(matrix().impact("IMPL.1"))=={"REQ.1","IMPL.1","TEST.1","EVID.1"}
def test_orphan_requirement_reported():
 m=TraceabilityMatrix((TraceNode("REQ.1",NodeKind.REQUIREMENT,"p"),),());assert m.orphan_requirements()==("REQ.1",)
def test_dangling_edge_rejected():
 with pytest.raises(TraceError,match="dangling"):TraceabilityMatrix((TraceNode("REQ.1",NodeKind.REQUIREMENT,"p"),),(TraceEdge("IMPL.9","REQ.1",EdgeKind.IMPLEMENTS),))
def test_contradictory_edge_types_rejected():
 ns=(TraceNode("REQ.1",NodeKind.REQUIREMENT,"p"),TraceNode("TEST.1",NodeKind.TEST,"t"))
 with pytest.raises(TraceError,match="contradictory"):TraceabilityMatrix(ns,(TraceEdge("TEST.1","REQ.1",EdgeKind.IMPLEMENTS),))
def test_self_edge_rejected():
 with pytest.raises(TraceError,match="self"):TraceEdge("REQ.1","REQ.1",EdgeKind.DEPENDS_ON)
