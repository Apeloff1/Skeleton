"""Graph projection for visual crawler terrain."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class CrawlGraphNode:
 url:str;depth:int;state:str;content_hash:str|None=None
@dataclass(frozen=True)
class CrawlGraphEdge:
 parent:str;child:str
class CrawlGraphProjection:
 def __init__(self):self.nodes={};self.edges=set()
 def apply(self,event):
  p=event.payload;kind=event.kind
  if kind=="frontier_discovered":
   self.nodes[event.url]=CrawlGraphNode(event.url,int(p.get("depth",0)),"discovered")
   if p.get("parent"):self.edges.add((p["parent"],event.url))
  elif event.url in self.nodes:
   old=self.nodes[event.url];state={"fetch_started":"acquiring","policy_rejected":"rejected","acquisition_accepted":"accepted","burn_complete":"indexed"}.get(kind,old.state)
   self.nodes[event.url]=CrawlGraphNode(old.url,old.depth,state,p.get("content_hash",old.content_hash))
 def snapshot(self):
  return (tuple(sorted(self.nodes.values(),key=lambda x:(x.depth,x.url))),tuple(CrawlGraphEdge(*x) for x in sorted(self.edges)))
