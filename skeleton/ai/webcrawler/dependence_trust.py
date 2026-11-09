"""Dependence-adjusted source trust: correlated evidence cannot multiply confidence freely."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ClusterTrust:
 cluster:tuple[str,...];trust:float
def dependence_adjusted_trust(observations,edges,posteriors):
 parent={x.observation_id:x.observation_id for x in observations}
 def root(x):
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 for e in edges:
  a,b=root(e.left_id),root(e.right_id)
  if a!=b:parent[max(a,b)]=min(a,b)
 groups={}
 by={x.observation_id:x for x in observations}
 for oid in parent:groups.setdefault(root(oid),[]).append(oid)
 out=[]
 for ids in groups.values():
  vals=[]
  for oid in ids:
   obs=by[oid];p=posteriors.get(obs.host);vals.append(float(p.mean) if p else .5)
  # Correlated members contribute only their strongest calibrated trust.
  out.append(ClusterTrust(tuple(sorted(ids)),max(vals,default=.5)))
 return tuple(sorted(out,key=lambda x:(-x.trust,x.cluster)))
