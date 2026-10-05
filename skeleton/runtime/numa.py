from dataclasses import dataclass
@dataclass(frozen=True)
class NUMANode: node_id:int; cpus:frozenset[int]; memory:int
@dataclass(frozen=True)
class NUMAAffinity: cpu:int; preferred_node:int
@dataclass(frozen=True)
class NUMAPlacement: node:int|None; fallback:bool
def place(nodes,affinity,required_memory):
 nodes=tuple(nodes)
 if isinstance(required_memory,bool) or not isinstance(required_memory,int) or required_memory<=0 or isinstance(affinity.cpu,bool) or affinity.cpu<0 or isinstance(affinity.preferred_node,bool) or affinity.preferred_node<0:raise ValueError("valid NUMA request required")
 ids=[x.node_id for x in nodes]
 if len(ids)!=len(set(ids)) or any(isinstance(x.node_id,bool) or x.node_id<0 or isinstance(x.memory,bool) or x.memory<0 or any(isinstance(c,bool) or c<0 for c in x.cpus) for x in nodes):raise ValueError("invalid NUMA topology")
 n=next((x for x in nodes if x.node_id==affinity.preferred_node and affinity.cpu in x.cpus and x.memory>=required_memory),None)
 if n:return NUMAPlacement(n.node_id,False)
 candidates=sorted((x for x in nodes if x.memory>=required_memory),key=lambda x:x.node_id)
 return NUMAPlacement(candidates[0].node_id,True) if candidates else NUMAPlacement(None,True)
