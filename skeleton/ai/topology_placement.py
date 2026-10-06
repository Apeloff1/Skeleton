"""Deterministic, fail-closed topology-aware placement for AI runtime workloads."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _digest(prefix,payload):
    return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _id(value,name):
    if not isinstance(value,str) or not value.strip(): raise ValueError(f"{name} is required")
    return value

def _uint(value,name):
    if isinstance(value,bool) or not isinstance(value,int) or value<0: raise ValueError(f"{name} must be a non-negative integer")
    return value

@dataclass(frozen=True)
class NumaNode:
    node_id:str; capacity_bytes:int; available_bytes:int; accelerator_ids:tuple[str,...]=()
    def __post_init__(self):
        _id(self.node_id,"node_id");_uint(self.capacity_bytes,"capacity_bytes");_uint(self.available_bytes,"available_bytes")
        if self.available_bytes>self.capacity_bytes: raise ValueError("available capacity exceeds node capacity")
        if len(set(self.accelerator_ids))!=len(self.accelerator_ids) or any(not x.strip() for x in self.accelerator_ids): raise ValueError("invalid accelerator identity")

@dataclass(frozen=True)
class TopologySnapshot:
    generation:int; captured_at_ns:int; expires_at_ns:int; nodes:tuple[NumaNode,...]; locality_evidence_id:str
    def __post_init__(self):
        _uint(self.generation,"generation");_uint(self.captured_at_ns,"captured_at_ns");_uint(self.expires_at_ns,"expires_at_ns");_id(self.locality_evidence_id,"locality_evidence_id")
        if self.expires_at_ns<=self.captured_at_ns: raise ValueError("topology expiry must follow capture")
        ids=[n.node_id for n in self.nodes]
        if not ids or len(ids)!=len(set(ids)): raise ValueError("topology requires unique nodes")
    @property
    def snapshot_id(self):
        return _digest("topology-sha256:",{"generation":self.generation,"captured_at_ns":self.captured_at_ns,"expires_at_ns":self.expires_at_ns,"locality_evidence_id":self.locality_evidence_id,"nodes":[{"node_id":n.node_id,"capacity_bytes":n.capacity_bytes,"available_bytes":n.available_bytes,"accelerator_ids":sorted(n.accelerator_ids)} for n in sorted(self.nodes,key=lambda x:x.node_id)]})

@dataclass(frozen=True)
class PlacementRequest:
    workload_id:str; required_bytes:int; preferred_node_ids:tuple[str,...]; required_accelerator_id:str|None; resource_lease_id:str; operation_id:str
    def __post_init__(self):
        _id(self.workload_id,"workload_id");_uint(self.required_bytes,"required_bytes");_id(self.resource_lease_id,"resource_lease_id");_id(self.operation_id,"operation_id")
        if self.required_bytes==0: raise ValueError("required_bytes must be positive")
        if len(set(self.preferred_node_ids))!=len(self.preferred_node_ids): raise ValueError("duplicate preferred node")
        if self.required_accelerator_id is not None: _id(self.required_accelerator_id,"required_accelerator_id")

@dataclass(frozen=True)
class PlacementReceipt:
    receipt_id:str; snapshot_id:str; topology_generation:int; workload_id:str; node_id:str; reserved_bytes:int; resource_lease_id:str; operation_id:str; locality_evidence_id:str

def place(request,snapshot,now_ns):
    _uint(now_ns,"now_ns")
    if now_ns<snapshot.captured_at_ns or now_ns>=snapshot.expires_at_ns: raise PermissionError("topology snapshot is not live")
    nodes={n.node_id:n for n in snapshot.nodes}
    unknown=[x for x in request.preferred_node_ids if x not in nodes]
    if unknown: raise PermissionError("preferred topology node is absent")
    ordered=list(request.preferred_node_ids)+[n.node_id for n in sorted(snapshot.nodes,key=lambda x:x.node_id) if n.node_id not in request.preferred_node_ids]
    candidates=[]
    for node_id in ordered:
        n=nodes[node_id]
        if n.available_bytes<request.required_bytes: continue
        if request.required_accelerator_id is not None and request.required_accelerator_id not in n.accelerator_ids: continue
        candidates.append(n)
    if not candidates: raise PermissionError("no topology placement satisfies capacity and locality")
    node=candidates[0]
    payload={"snapshot_id":snapshot.snapshot_id,"topology_generation":snapshot.generation,"workload_id":request.workload_id,"node_id":node.node_id,"reserved_bytes":request.required_bytes,"resource_lease_id":request.resource_lease_id,"operation_id":request.operation_id,"locality_evidence_id":snapshot.locality_evidence_id}
    return PlacementReceipt(_digest("placement-sha256:",payload),snapshot.snapshot_id,snapshot.generation,request.workload_id,node.node_id,request.required_bytes,request.resource_lease_id,request.operation_id,snapshot.locality_evidence_id)

def validate_receipt(receipt,request,snapshot,now_ns):
    expected=place(request,snapshot,now_ns)
    if receipt!=expected: raise PermissionError("placement receipt does not match live topology")
    return True
