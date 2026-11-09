"""Deterministic learner-facing knowledge graph and state."""
from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
from typing import Sequence
class RelationKind(str,Enum):
 PREREQUISITE="prerequisite"; PART_OF="part_of"; INSTANCE_OF="instance_of"; RELATED="related"; CONTRASTS="contrasts"; CAUSES="causes"; SUPPORTS="supports"; APPLIES_TO="applies_to"; EXAMPLE_OF="example_of"; TRANSFERS_TO="transfers_to"
@dataclass(frozen=True)
class KnowledgeNode: node_id:str; title:str; description:str=""; tags:tuple[str,...]=(); difficulty:float=.5; source_ids:tuple[str,...]=()
@dataclass(frozen=True)
class KnowledgeEdge: source:str; target:str; relation:RelationKind; weight:float=1.; source_id:str=""
@dataclass(frozen=True)
class KnowledgeAssertion: assertion_id:str; subject:str; predicate:str; object:str; confidence:float=1.; source_id:str=""; evidence:tuple[str,...]=()
@dataclass
class KnowledgeGraph:
 nodes:dict[str,KnowledgeNode]=field(default_factory=dict); edges:list[KnowledgeEdge]=field(default_factory=list); assertions:dict[str,KnowledgeAssertion]=field(default_factory=dict)
 def add_node(self,node): self.nodes[node.node_id]=node
 def add_edge(self,edge):
  if edge.source not in self.nodes or edge.target not in self.nodes: raise ValueError("knowledge edge endpoints must exist")
  if not 0<=edge.weight<=1: raise ValueError("edge weight must be in [0, 1]")
  self.edges.append(edge)
 def add_assertion(self,a):
  if a.subject not in self.nodes: raise ValueError("assertion subject must exist")
  self.assertions[a.assertion_id]=a
 def neighbors(self,node_id,relation=None): return tuple(e for e in self.edges if e.source==node_id and (relation is None or e.relation==relation))
 def prerequisites(self,node_id): return tuple(e.target for e in self.neighbors(node_id,RelationKind.PREREQUISITE))
 def ancestors(self,node_id,max_depth=32):
  seen=set(); frontier=[(node_id,0)]
  while frontier:
   cur,depth=frontier.pop()
   if depth>=max_depth: continue
   for e in self.neighbors(cur,RelationKind.PREREQUISITE):
    if e.target not in seen: seen.add(e.target); frontier.append((e.target,depth+1))
  return tuple(sorted(seen))
 def validate(self):
  for node in self.nodes: self._validate_acyclic(node)
 def _validate_acyclic(self,start):
  visiting=set(); visited=set()
  def visit(n):
   if n in visiting: raise ValueError("knowledge prerequisite cycle")
   if n in visited:return
   visiting.add(n)
   for target in self.prerequisites(n): visit(target)
   visiting.remove(n); visited.add(n)
  visit(start)
@dataclass
class KnowledgeState:
 confidence:dict[str,float]=field(default_factory=dict); exposure:dict[str,int]=field(default_factory=dict); evidence:dict[str,list[str]]=field(default_factory=dict); misconceptions:dict[str,str]=field(default_factory=dict)
 def observe(self,node_id,score,*,evidence=""):
  score=max(0.,min(1.,score)); prior=self.confidence.get(node_id,0.); count=self.exposure.get(node_id,0); alpha=.6 if count==0 else 1./min(8,count+2)
  self.confidence[node_id]=prior*(1-alpha)+score*alpha; self.exposure[node_id]=count+1
  if evidence:self.evidence.setdefault(node_id,[]).append(evidence)
 def mark_misconception(self,node_id,description): self.misconceptions[node_id]=description
 def mastery(self,node_id): return max(0.,min(1.,self.confidence.get(node_id,0.)))
 def ready_for(self,graph,node_id,threshold=.7): return all(self.mastery(p)>=threshold for p in graph.prerequisites(node_id))
@dataclass(frozen=True)
class KnowledgeCandidate: node_id:str; score:float; reason:str; path:tuple[str,...]=()
def rank_knowledge(graph,state,*,query_terms=(),goals=(),limit=8):
 terms={t.casefold() for t in query_terms if t.strip()}; goal_set={g.casefold() for g in goals}; out=[]
 for node in graph.nodes.values():
  text=" ".join((node.node_id,node.title,node.description,*node.tags)).casefold(); lexical=sum(1 for t in terms if t in text)/max(1,len(terms)); goal=.25 if any(g in text for g in goal_set) else 0.; gap=1-state.mastery(node.node_id); ready=.2 if state.ready_for(graph,node.node_id) else -.25; repair=.35 if node.node_id in state.misconceptions else 0.; score=.45*gap+.25*lexical+goal+ready+repair; reason="misconception repair" if node.node_id in state.misconceptions else ("query-aligned knowledge" if lexical else "learning gap"); out.append(KnowledgeCandidate(node.node_id,score,reason,graph.ancestors(node.node_id)))
 return tuple(sorted(out,key=lambda x:(-x.score,x.node_id))[:limit])
def infer_ready_frontier(graph,state,*,threshold=.7): return tuple(n.node_id for n in sorted(graph.nodes.values(),key=lambda x:x.node_id) if state.mastery(n.node_id)<threshold and state.ready_for(graph,n.node_id,threshold))
