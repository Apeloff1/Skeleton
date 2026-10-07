from dataclasses import dataclass
@dataclass(frozen=True)
class ImpactQuery: changed:tuple[str,...]
@dataclass(frozen=True)
class ImpactEvidence: source:str; edge_count:int; complete:bool
@dataclass(frozen=True)
class ImpactSet: affected:tuple[str,...]; owners:tuple[str,...]; tests:tuple[str,...]; uncertainty:float; evidence:tuple[ImpactEvidence,...]
def analyze_impact(q,graphs,owners,tests):
 if not q.changed or any(not x for x in q.changed) or len(q.changed)!=len(set(q.changed)):raise ValueError("unique changed artifact identities required")
 affected=set(q.changed);ev=[];complete=True
 for name,g,is_complete in graphs:
  if not name or not isinstance(is_complete,bool):raise ValueError("graph evidence identity/completeness required")
  ev.append(ImpactEvidence(name,sum(len(v) for v in g.values()),is_complete));complete &= is_complete
  frontier=list(affected)
  while frontier:
   x=frontier.pop()
   for y in g.get(x,()):
    if y not in affected:affected.add(y);frontier.append(y)
 own=tuple(sorted({owners[x] for x in affected if x in owners}));ts=tuple(sorted({t for x in affected for t in tests.get(x,())}))
 return ImpactSet(tuple(sorted(affected)),own,ts,0.0 if complete else 1.0,tuple(ev))
