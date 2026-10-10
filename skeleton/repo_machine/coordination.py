"""Repository-scale coordination over a shared work graph."""
from __future__ import annotations
from dataclasses import dataclass
from .model import RepositoryModel
from .workgraph import WorkGraph, WorkNode, build_work_graph

@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    work_identity:str; action:str; strategic_score:int; unlock_potential:int; confidence:int; blocked:bool; reasons:tuple[str,...]
    coordination_pressure:int=0; parallelism:int=0; downstream_value:int=0; conflict_density:int=0; influence:int=0; risk_adjusted_influence:int=0; verification_efficiency:int=0; counterfactual_unlock:int=0; decision_margin:int=0
    def as_dict(self)->dict[str,object]:
        return {"work_identity":self.work_identity,"action":self.action,"strategic_score":self.strategic_score,"unlock_potential":self.unlock_potential,
                "confidence":self.confidence,"blocked":self.blocked,"reasons":list(self.reasons),
                "coordination_pressure":self.coordination_pressure,"parallelism":self.parallelism,
                "downstream_value":self.downstream_value,"conflict_density":self.conflict_density,"influence":self.influence,"risk_adjusted_influence":self.risk_adjusted_influence,"verification_efficiency":self.verification_efficiency,"counterfactual_unlock":self.counterfactual_unlock,"decision_margin":self.decision_margin}

@dataclass(frozen=True, slots=True)
class CoordinationPlan:
    repository_fingerprint:str; decisions:tuple[CoordinationDecision,...]; bottleneck:str|None; frontier_size:int; max_parallelism:int=0; coordination_pressure:int=0; graph_fingerprint:str=""; safe_parallel_groups:tuple[tuple[str,...],...]=()
    def as_dict(self)->dict[str,object]:
        ranked=rank_decisions(self,limit=len(self.decisions)) if self.decisions else ()
        return {"repository_fingerprint":self.repository_fingerprint,"decisions":[d.as_dict() for d in self.decisions],"ranked_decisions":[d.as_dict() for d in ranked],"bottleneck":self.bottleneck,
                "frontier_size":self.frontier_size,"max_parallelism":self.max_parallelism,"coordination_pressure":self.coordination_pressure,"graph_fingerprint":self.graph_fingerprint,
                "safe_parallel_groups":[list(group) for group in self.safe_parallel_groups]}

def _confidence(node:WorkNode)->int:
    value=node.topology_confidence+(10 if node.verification_paths else 0)-(10 if node.readiness=="gated" else 0)+min(10,node.decision_score//10)
    return min(100,max(0,value))

def _decision(node:WorkNode,graph:WorkGraph,blocked=False)->CoordinationDecision:
    confidence=_confidence(node); pressure=graph.node_pressure(node.identity); parallel=graph.parallelism_hint(node.identity)
    downstream=graph.downstream_value(node.identity); conflicts=graph.conflict_density(node.identity); influence=graph.influence(node.identity)
    risk_adjusted=graph.risk_adjusted_influence(node.identity); efficiency=graph.verification_efficiency(node.identity); counterfactual=graph.counterfactual_unlock(node.identity); margin=graph.decision_margin(node.identity)
    reasons=[f"strategic score={node.strategic_score}",f"unlock potential={node.unlock_potential}",
             f"downstream value={downstream}",f"coordination pressure={pressure}",
             f"conflict density={conflicts}",f"influence={influence}",f"risk-adjusted influence={risk_adjusted}",f"verification efficiency={efficiency}",f"counterfactual unlock={counterfactual}",f"decision margin={margin}",f"parallelism={parallel}"]
    if node.critical_path_depth: reasons.append(f"critical-path depth={node.critical_path_depth}")
    if node.blast_radius: reasons.append(f"blast radius={node.blast_radius}")
    if blocked: reasons.append("blocked by unmet prerequisites")
    if confidence<40: reasons.append("low topology confidence requires conservative verification")
    elif confidence>=80: reasons.append("strong topology confidence supports direct execution")
    action="inspect-then-verify" if confidence<40 else ("wait-for-prerequisite" if blocked else "execute-and-verify")
    return CoordinationDecision(node.identity,action,node.strategic_score,node.unlock_potential,confidence,blocked,tuple(reasons),
                                 pressure,parallel,downstream,conflicts,influence,risk_adjusted,efficiency,counterfactual,margin)

def rank_decisions(plan:CoordinationPlan,*,limit:int=8)->tuple[CoordinationDecision,...]:
    """Return bounded decisions ordered by independent counterfactual value signals."""
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=64: raise ValueError("limit must be in [1,64]")
    return tuple(sorted(plan.decisions,key=lambda d:(d.blocked,-d.risk_adjusted_influence,-d.counterfactual_unlock,-d.decision_margin,-d.verification_efficiency,-d.downstream_value,d.work_identity))[:limit])

def select_next_work(model:RepositoryModel,*,completed:tuple[str,...]=(),active_conflicts:tuple[str,...]=(),limit:int=8,graph:WorkGraph|None=None)->CoordinationPlan:
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=64: raise ValueError("limit must be in [1,64]")
    graph=graph or build_work_graph(model,limit=max(limit,32))
    ready=graph.ready(completed,active_conflicts,limit=limit); blocked=graph.blocked(completed)
    decisions=tuple(_decision(n,graph) for n in ready)
    if len(decisions)<limit: decisions+=tuple(_decision(n,graph,True) for n in blocked[:limit-len(decisions)])
    groups=graph.safe_parallel_groups(completed,limit=min(8,limit))
    return CoordinationPlan(model.fingerprint,decisions,graph.bottleneck(completed),len(graph.frontier(completed)),graph.max_parallelism(completed),
                            graph.pressure(),graph.fingerprint,groups)

def build_coordination_plan(model:RepositoryModel,*,limit:int=8,graph:WorkGraph|None=None)->dict[str,object]:
    return select_next_work(model,limit=limit,graph=graph).as_dict()

__all__=["CoordinationDecision","CoordinationPlan","build_coordination_plan","rank_decisions","select_next_work"]
