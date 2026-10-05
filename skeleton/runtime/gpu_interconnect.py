from dataclasses import dataclass
import math
@dataclass(frozen=True)
class GPUInterconnect:
 a:str; b:str; bandwidth:float; measured:bool
 def __post_init__(self):
  if not self.a or not self.b or self.a==self.b or isinstance(self.bandwidth,bool) or not isinstance(self.bandwidth,(int,float)) or not math.isfinite(self.bandwidth) or self.bandwidth<=0:raise ValueError("valid GPU link required")
@dataclass(frozen=True)
class GPUPath: devices:tuple[str,...]; bottleneck:float
@dataclass(frozen=True)
class CollectivePlacement: devices:tuple[str,...]; evidence:tuple[GPUInterconnect,...]
def place_collective(devices,links):
 chosen=tuple(devices)
 if len(chosen)<2 or len(chosen)!=len(set(chosen)):raise ValueError("distinct collective devices required")
 ls=tuple(links);needed=[]
 for i,a in enumerate(chosen):
  for b in chosen[i+1:]:
   x=next((l for l in ls if {l.a,l.b}=={a,b} and l.measured is True),None)
   if not x:raise ValueError("collective requires measured pairwise interconnect")
   needed.append(x)
 return CollectivePlacement(chosen,tuple(needed))
