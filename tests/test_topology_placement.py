import pytest
from skeleton.ai.topology_placement import NumaNode,TopologySnapshot,PlacementRequest,place,validate_receipt

def snap(**kw):
 d=dict(generation=4,captured_at_ns=100,expires_at_ns=200,nodes=(NumaNode("n0",8192,4096,("gpu0",)),NumaNode("n1",8192,6144,("gpu1",))),locality_evidence_id="locality:e1");d.update(kw);return TopologySnapshot(**d)
def req(**kw):
 d=dict(workload_id="w1",required_bytes=2048,preferred_node_ids=("n0",),required_accelerator_id="gpu0",resource_lease_id="lease:7",operation_id="op:9");d.update(kw);return PlacementRequest(**d)

def test_placement_is_deterministic_and_prefers_local_node():
 a=place(req(),snap(),150);b=place(req(),snap(),150);assert a==b;assert a.node_id=="n0";assert a.receipt_id.startswith("placement-sha256:")

@pytest.mark.parametrize("now",[99,200,201])
def test_stale_or_preissue_topology_fails_closed(now):
 with pytest.raises(PermissionError): place(req(),snap(),now)

def test_capacity_and_accelerator_requirements_fail_closed():
 with pytest.raises(PermissionError): place(req(required_bytes=7000),snap(),150)
 with pytest.raises(PermissionError): place(req(required_accelerator_id="gpu9"),snap(),150)

def test_unknown_preference_is_not_silently_ignored():
 with pytest.raises(PermissionError): place(req(preferred_node_ids=("n9",)),snap(),150)

def test_generation_change_invalidates_receipt():
 r=place(req(),snap(),150)
 with pytest.raises(PermissionError): validate_receipt(r,req(),snap(generation=5),150)

def test_locality_evidence_change_invalidates_receipt():
 r=place(req(),snap(),150)
 with pytest.raises(PermissionError): validate_receipt(r,req(),snap(locality_evidence_id="locality:e2"),150)

def test_lease_or_operation_substitution_invalidates_receipt():
 r=place(req(),snap(),150)
 with pytest.raises(PermissionError): validate_receipt(r,req(resource_lease_id="lease:8"),snap(),150)
 with pytest.raises(PermissionError): validate_receipt(r,req(operation_id="op:10"),snap(),150)

def test_snapshot_identity_is_order_independent():
 s=snap();rev=snap(nodes=tuple(reversed(s.nodes)));assert s.snapshot_id==rev.snapshot_id
