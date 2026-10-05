from dataclasses import dataclass
@dataclass(frozen=True)
class NUMANode: node_id:int; cpus:frozenset[int]; memory:int
@dataclass(frozen=True)
class NUMAAffinity: cpu:int; preferred_node:int
@dataclass(frozen=True)
class NUMAPlacement: node:int|None; fallback:bool
def place(nodes,affinity,required_memory):
 n=next((x for x in nodes if x.node_id==affinity.preferred_node and affinity.cpu in x.cpus and x.memory>=required_memory),None)
 if n:return NUMAPlacement(n.node_id,False)
 candidates=sorted((x for x in nodes if x.memory>=required_memory),key=lambda x:x.node_id)
 return NUMAPlacement(candidates[0].node_id,True) if candidates else NUMAPlacement(None,True)
