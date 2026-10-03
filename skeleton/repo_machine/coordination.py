"""Repository-scale coordination over a shared work graph."""
from __future__ import annotations
from dataclasses import dataclass
from .model import RepositoryModel
from .workgraph import WorkGraph, WorkNode, build_work_graph

@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    work_identity:str; action:str; strategic_score:int; unlock_potential:int; confidence:int; blocked:bool; reasons:tuple[str,...]
    coordination_pressure:int=0; parallelism:int=0
    def as_dict(self)->dict[str,object]:
        return {"work_identity":self.work_identity,"action":self.action,"strategic_score":self.strategic_score,"unlock_potential":self.unlock_potential,
                "confidence":self.confidence,"blocked":self.blocked,"reasons":list(self.reasons),"coordination_pressure":self.coordination_pressure,"parallelism":self.parallelism}

@dataclass(frozen=True, slots=True)
class CoordinationPlan:
    repository_fingerprint:str; decisions:tuple[CoordinationDecision,...]; bottleneck:str|None; frontier_size:int; max_parallelism:int=0; coordination_pressure:int=0
    def as_dict(self)->dict[str,object]:
        return {"repository_fingerprint":self.repository_fingerprint,"decisions":[d.as_dict() for d in self.decisions],"bottleneck":self.bottleneck,
                "frontier_size":self.frontier_size,"max_parallelism":self.max_parallelism,"coordination_pressure":self.coordination_pressure}

def _confidence(node:WorkNode)->int:
    value=node.topology_confidence+(10 if node.verification_paths else 0)-(10 if node.readiness=="gated" else 0)+min(10,node.decision_score//10)
    return min(100,max(0,value))

def _pressure(node:WorkNode,graph:WorkGraph)->int:
    return min(100,node.unlock_potential*6+node.blast_radius*3+len(node.conflict_keys)*2+(20 if node.critical_path_depth else 0))

def _decision(node:WorkNode,graph:WorkGraph,blocked=False)->CoordinationDecision:
    confidence=_confidence(node); pressure=_pressure(node,graph); parallel=graph.parallelism_hint(node.identity)
    reasons=[f"strategic score={node.strategic_score}",f"unlock potential={node.unlock_potential}",f"coordination pressure={pressure}",f"parallelism={parallel}"]
    if node.critical_path_depth: reasons.append(f"critical-path depth={node.critical_path_depth}")
    if node.blast_radius: reasons.append(f"blast radius={node.blast_radius}")
    if blocked: reasons.append("blocked by unmet prerequisites")
    if confidence<40: reasons.append("low topology confidence requires conservative verification")
    elif confidence>=80: reasons.append("strong topology confidence supports direct execution")
    action="inspect-then-verify" if confidence<40 else ("wait-for-prerequisite" if blocked else "execute-and-verify")
    return CoordinationDecision(node.identity,action,node.strategic_score,node.unlock_potential,confidence,blocked,tuple(reasons),pressure,parallel)

def select_next_work(model:RepositoryModel,*,completed:tuple[str,...]=(),active_conflicts:tuple[str,...]=(),limit:int=8,graph:WorkGraph|None=None)->CoordinationPlan:
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=64: raise ValueError("limit must be in [1,64]")
    graph=graph or build_work_graph(model,limit=max(limit,32))
    ready=graph.ready(completed,active_conflicts,limit=limit); blocked=graph.blocked(completed)
    decisions=tuple(_decision(n,graph) for n in ready)
    if len(decisions)<limit: decisions+=tuple(_decision(n,graph,True) for n in blocked[:limit-len(decisions)])
    return CoordinationPlan(model.fingerprint,decisions,graph.bottleneck(completed),len(graph.frontier(completed)),graph.max_parallelism(completed),
                            graph.pressure())

def build_coordination_plan(model:RepositoryModel,*,limit:int=8,graph:WorkGraph|None=None)->dict[str,object]:
    return select_next_work(model,limit=limit,graph=graph).as_dict()

__all__=["CoordinationDecision","CoordinationPlan","build_coordination_plan","select_next_work"]
