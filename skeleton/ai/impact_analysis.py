from dataclasses import dataclass
@dataclass(frozen=True)
class ImpactQuery: changed:tuple[str,...]
@dataclass(frozen=True)
class ImpactEvidence: source:str; complete:bool
@dataclass(frozen=True)
class ImpactSet: affected:tuple[str,...]; uncertainty:float; evidence:tuple[ImpactEvidence,...]
def analyze_impact(q,graphs):
 affected=set(q.changed);evidence=[]
 for name,g,complete in graphs:
  evidence.append(ImpactEvidence(name,complete));front=list(affected)
  while front:
   x=front.pop()
   for y in g.get(x,()):
    if y not in affected:affected.add(y);front.append(y)
 return ImpactSet(tuple(sorted(affected)),0.0 if all(x.complete for x in evidence) else 1.0,tuple(evidence))
