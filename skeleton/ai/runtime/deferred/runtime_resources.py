"""Runtime resource, cache and topology controls VOL-383,384,387-389,393-394."""
from dataclasses import dataclass
@dataclass(frozen=True,slots=True)
class GPUMemoryPool: gpu_id:str; capacity:int; free_segments:tuple[tuple[int,int],...]
@dataclass(frozen=True,slots=True)
class GPUMemoryReservation: reservation_id:str; gpu_id:str; offset:int; size:int
@dataclass(frozen=True,slots=True)
class GPUAllocation: pool:GPUMemoryPool; reservation:GPUMemoryReservation|None
def reserve_gpu(p,reservation_id,size):
 if not p.gpu_id or p.capacity<=0 or not reservation_id or size<=0:raise ValueError("valid GPU reservation identity and capacity required")
 if any(off<0 or length<=0 or off+length>p.capacity for off,length in p.free_segments):raise ValueError("invalid GPU free segment")
 candidates=sorted((length,start) for start,length in p.free_segments if length>=size)
 if not candidates:return GPUAllocation(p,None)
 _,start=candidates[0];segs=[]
 for off,length in p.free_segments:
  if off==start:segs.extend(((off+size,length-size),) if length>size else ())
  else:segs.append((off,length))
 r=GPUMemoryReservation(reservation_id,p.gpu_id,start,size)
 return GPUAllocation(GPUMemoryPool(p.gpu_id,p.capacity,tuple(sorted(segs))),r)
@dataclass(frozen=True,slots=True)
class EvictionPolicy: require_idle:bool=True
@dataclass(frozen=True,slots=True)
class DrainState: model_id:str; pinned:bool; in_flight:int
@dataclass(frozen=True,slots=True)
class ModelEviction: model_id:str; allowed:bool; reason:str; reloadable:bool=True
def evict_model(s,p=EvictionPolicy()):
 if not s.model_id or s.in_flight<0:raise ValueError("invalid drain state")
 if s.pinned:return ModelEviction(s.model_id,False,"pinned")
 if p.require_idle and s.in_flight:return ModelEviction(s.model_id,False,"in-flight")
 return ModelEviction(s.model_id,True,"safe boundary")
@dataclass(frozen=True,slots=True)
class KVCacheKey: model:str; config:str; token_prefix:str; session:str; tenant:str; privacy_scope:str
@dataclass(frozen=True,slots=True)
class KVCacheEntry: key:KVCacheKey; payload_digest:str
@dataclass(frozen=True,slots=True)
class KVCacheLease: key:KVCacheKey; tenant:str; active:bool
def kv_reusable(e,key):return e.key==key
@dataclass(frozen=True,slots=True)
class PrefixCacheKey: instruction:str; prompt:str; model:str; tokenizer:str; version:str; authorization_scope:str
@dataclass(frozen=True,slots=True)
class PrefixArtifact: key:PrefixCacheKey; digest:str; sensitive:bool
@dataclass(frozen=True,slots=True)
class PrefixReuseDecision: allowed:bool; reason:str
def prefix_reuse(a,k):
 if a.key!=k:return PrefixReuseDecision(False,"identity mismatch")
 if a.sensitive and a.key.authorization_scope!=k.authorization_scope:return PrefixReuseDecision(False,"scope mismatch")
 return PrefixReuseDecision(True,"exact match")
@dataclass(frozen=True,slots=True)
class DraftToken: token_id:int; accepted:bool=False
@dataclass(frozen=True,slots=True)
class VerificationStep: token_id:int; target_accepted:bool
@dataclass(frozen=True,slots=True)
class SpeculativePlan: draft_model:str; target_model:str; fallback:bool=True
def verify_draft(tokens,checks):
 if len(tokens)!=len(checks):raise ValueError("draft verification length mismatch")
 if any(t.token_id!=c.token_id for t,c in zip(tokens,checks)):raise ValueError("draft verification identity mismatch")
 return tuple(t.token_id for t,c in zip(tokens,checks) if c.target_accepted)
@dataclass(frozen=True,slots=True)
class NUMANode: node_id:str; cpu_ids:tuple[int,...]; memory_bytes:int
@dataclass(frozen=True,slots=True)
class NUMAAffinity: node_id:str; measured_benefit:float|None
@dataclass(frozen=True,slots=True)
class NUMAPlacement: node_id:str|None; topology_used:bool
def numa_place(nodes,affinity):
 if not nodes or affinity.measured_benefit is None:return NUMAPlacement(None,False)
 return NUMAPlacement(affinity.node_id,True) if any(n.node_id==affinity.node_id for n in nodes) else NUMAPlacement(None,False)
@dataclass(frozen=True,slots=True)
class GPUInterconnect: source:str; target:str; bandwidth:float; measured:bool
@dataclass(frozen=True,slots=True)
class GPUPath: devices:tuple[str,...]; bottleneck_bandwidth:float
@dataclass(frozen=True,slots=True)
class CollectivePlacement: path:GPUPath|None; admitted:bool
def collective_path(edges,devices):
 relevant=[e for e in edges if e.measured and e.source in devices and e.target in devices]
 if len(devices)<2:return CollectivePlacement(GPUPath(tuple(devices),float("inf")),True)
 if not relevant:return CollectivePlacement(None,False)
 graph={d:set() for d in devices}
 for e in relevant:
  if e.bandwidth<=0:continue
  graph[e.source].add(e.target);graph[e.target].add(e.source)
 seen={devices[0]};front=[devices[0]]
 while front:
  n=front.pop()
  for x in graph[n]:
   if x not in seen:seen.add(x);front.append(x)
 if seen!=set(devices):return CollectivePlacement(None,False)
 return CollectivePlacement(GPUPath(tuple(devices),min(e.bandwidth for e in relevant if e.bandwidth>0)),True)
