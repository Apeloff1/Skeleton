"""Citation/reference lineage for research evidence."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urljoin
import re
_URL=re.compile(r'https?://[^\s<>"\']+')
@dataclass(frozen=True)
class CitationEdge:
 source_id:str;target_url:str;kind:str
def extract_citation_edges(observations):
 out=[]
 for obs in observations:
  seen=set()
  for raw in _URL.findall(obs.excerpt):
   url=raw.rstrip(".,);]")
   if url==obs.canonical_url or url in seen:continue
   seen.add(url);out.append(CitationEdge(obs.observation_id,url,"explicit-url"))
 return tuple(sorted(out,key=lambda x:(x.source_id,x.target_url)))
def citation_dependence(observations,edges):
 by_url={x.canonical_url:x.observation_id for x in observations};out=set()
 for e in edges:
  target=by_url.get(e.target_url)
  if target and target!=e.source_id:out.add(tuple(sorted((e.source_id,target))))
 return tuple(sorted(out))
