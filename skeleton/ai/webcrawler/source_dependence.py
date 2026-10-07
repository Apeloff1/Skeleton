"""Detect source dependence so mirrored evidence is not counted as corroboration."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlsplit
import re
_WORD=re.compile(r"[a-z0-9]{3,}",re.I)
@dataclass(frozen=True)
class DependenceEdge:
 left_id:str;right_id:str;score:float;reasons:tuple[str,...]
def source_dependence(observations,*,threshold=.72):
 out=[];vals=tuple(observations)
 for i,a in enumerate(vals):
  ta=set(_WORD.findall(a.excerpt.lower()))
  for b in vals[i+1:]:
   tb=set(_WORD.findall(b.excerpt.lower()));union=len(ta|tb);j=len(ta&tb)/max(1,union)
   reasons=[];score=j
   if a.content_hash==b.content_hash:score=1.;reasons.append("identical-content")
   if a.host==b.host:score=max(score,.85);reasons.append("same-host")
   if j>=.6:reasons.append("high-text-overlap")
   if score>=threshold:out.append(DependenceEdge(a.observation_id,b.observation_id,min(1,score),tuple(reasons)))
 return tuple(out)
def merge_citation_dependence(observations,edges,citation_pairs):
 by={x.observation_id:x for x in observations};merged=list(edges);known={tuple(sorted((e.left_id,e.right_id))) for e in edges}
 for a,b in citation_pairs:
  pair=tuple(sorted((a,b)))
  if pair not in known and a in by and b in by:merged.append(DependenceEdge(a,b,1.0,("direct-citation",)))
 return tuple(sorted(merged,key=lambda e:(e.left_id,e.right_id,e.reasons)))

def independent_host_count(observations,edges):
 parent={x.observation_id:x.observation_id for x in observations}
 def root(x):
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 for e in edges:
  a,b=root(e.left_id),root(e.right_id)
  if a!=b:parent[max(a,b)]=min(a,b)
 clusters={}
 by={x.observation_id:x for x in observations}
 for oid in parent:clusters.setdefault(root(oid),set()).add(by[oid].host)
 return len(clusters)
