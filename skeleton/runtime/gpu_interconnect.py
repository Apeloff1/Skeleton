from dataclasses import dataclass
@dataclass(frozen=True)
class GPUInterconnect: a:str; b:str; bandwidth:float; measured:bool
@dataclass(frozen=True)
class GPUPath: devices:tuple[str,...]; bottleneck:float
@dataclass(frozen=True)
class CollectivePlacement: devices:tuple[str,...]; evidence:tuple[GPUInterconnect,...]
def place_collective(devices,links):
 chosen=tuple(sorted(devices));needed=[]
 for a,b in zip(chosen,chosen[1:]):
  x=next((l for l in links if {l.a,l.b}=={a,b} and l.measured),None)
  if not x:raise ValueError("unmeasured interconnect")
  needed.append(x)
 return CollectivePlacement(chosen,tuple(needed))
