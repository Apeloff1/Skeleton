"""Conflict-aware work graph with dependency, frontier, critical-path, and parallelism intelligence."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable
from .model import RepositoryModel
from .planner import WorkCandidate, derive_work_candidates

@dataclass(frozen=True, slots=True)
class WorkNode:
    identity:str; lane:str; zone:str; priority:int; objective:str; conflict_keys:tuple[str,...]; prerequisites:tuple[str,...]; evidence:tuple[str,...]
    verification_paths:tuple[str,...]=(); readiness:str="ready"; decision_score:int=0; topology_confidence:int=0; blast_radius:int=0
    critical_path_depth:int=0; unlock_potential:int=0; strategic_score:int=0
    def as_dict(self)->dict[str,object]:
        return {"identity":self.identity,"lane":self.lane,"zone":self.zone,"priority":self.priority,"objective":self.objective,
                "conflict_keys":list(self.conflict_keys),"prerequisites":list(self.prerequisites),"evidence":list(self.evidence),
                "verification_paths":list(self.verification_paths),"readiness":self.readiness,"decision_score":self.decision_score,
                "topology_confidence":self.topology_confidence,"blast_radius":self.blast_radius,"critical_path_depth":self.critical_path_depth,
                "unlock_potential":self.unlock_potential,"strategic_score":self.strategic_score}

@dataclass(frozen=True, slots=True)
class WorkGraph:
    nodes:tuple[WorkNode,...]
    _ordered_nodes:tuple[WorkNode,...]=field(init=False,repr=False,compare=False)
    _by_identity:dict[str,WorkNode]=field(init=False,repr=False,compare=False)
    _depth:dict[str,int]=field(init=False,repr=False,compare=False)
    _descendants:dict[str,frozenset[str]]=field(init=False,repr=False,compare=False)
    def __post_init__(self)->None:
        ordered=tuple(sorted(self.nodes,key=lambda n:(-n.priority,n.identity))); ids={n.identity for n in ordered}
        if len(ids)!=len(ordered): raise ValueError("work graph contains duplicate identities")
        by={n.identity:n for n in ordered}
        for n in ordered:
            if any(p not in by for p in n.prerequisites): raise ValueError(f"work graph has unknown prerequisites for {n.identity}")
        visiting=set(); visited=set(); depth={}; descendants={i:set() for i in by}
        def visit(i):
            if i in visiting: raise ValueError(f"work graph contains prerequisite cycle at {i}")
            if i in visited: return depth[i]
            visiting.add(i); d=0
            for p in by[i].prerequisites:
                d=max(d,visit(p)+1); descendants[p].add(i); descendants[p].update(descendants[i])
            visiting.remove(i); visited.add(i); depth[i]=d; return d
        for i in by: visit(i)
        max_depth=max(depth.values(),default=0); enriched=[]
        for n in ordered:
            unlock=len(descendants[n.identity])
            strategic=min(100,max(0,n.decision_score+min(25,unlock*5)+min(15,depth[n.identity]*3)+min(10,n.blast_radius*2)+min(10,n.topology_confidence//10)+(10 if max_depth and depth[n.identity]==max_depth else 0)))
            enriched.append(WorkNode(n.identity,n.lane,n.zone,n.priority,n.objective,n.conflict_keys,n.prerequisites,n.evidence,n.verification_paths,n.readiness,n.decision_score,n.topology_confidence,n.blast_radius,depth[n.identity],unlock,strategic))
        object.__setattr__(self,"_ordered_nodes",tuple(enriched)); object.__setattr__(self,"_by_identity",{n.identity:n for n in enriched})
        object.__setattr__(self,"_depth",depth); object.__setattr__(self,"_descendants",{k:frozenset(v) for k,v in descendants.items()})
    def as_dict(self): return {"nodes":[n.as_dict() for n in self._ordered_nodes],"frontier":[n.identity for n in self.frontier()],"critical_path_depth":max(self._depth.values(),default=0)}
    def frontier(self,completed:Iterable[str]=()):
        done=set(completed)
        return tuple(
            sorted(
                (
                    n
                    for n in self._ordered_nodes
                    if n.identity not in done
                    and all(p in done for p in n.prerequisites)
                ),
                key=lambda n:(-n.strategic_score,-n.priority,n.identity),
            )
        )
    def ready(self,completed=(),active_conflicts=(),*,limit=8):
        done=set(completed); unknown=done-set(self._by_identity)
        if unknown: raise ValueError("completed contains unknown work identities")
        conflicts=set(active_conflicts); selected=[]
        for n in self.frontier(done):
            if any(k in conflicts for k in n.conflict_keys): continue
            selected.append(n); conflicts.update(n.conflict_keys)
            if len(selected)>=limit: break
        return tuple(selected)
    def blocked(self,completed=()):
        done=set(completed); return tuple(n for n in self._ordered_nodes if n.identity not in done and any(p not in done for p in n.prerequisites))
    def unlock_potential(self,identity):
        if identity not in self._by_identity: raise ValueError(f"unknown work identity: {identity}")
        return len(self._descendants[identity])
    def critical_path(self):
        if not self._ordered_nodes:return ()
        terminal=max(self._ordered_nodes,key=lambda n:(self._depth[n.identity],n.strategic_score,n.priority,n.identity)); path=[terminal]
        while path[-1].prerequisites:
            path.append(max((self._by_identity[p] for p in path[-1].prerequisites),key=lambda n:(self._depth[n.identity],n.strategic_score,n.priority,n.identity)))
        return tuple(reversed(path))
    def bottleneck(self,completed=()):
        frontier=self.frontier(completed)
        if not frontier:return None
        return max(frontier,key=lambda n:(len(self._descendants[n.identity]),self._depth[n.identity],n.strategic_score,n.priority,n.identity)).identity
    def parallelism_hint(self,identity):
        if identity not in self._by_identity: raise ValueError(f"unknown work identity: {identity}")
        n=self._by_identity[identity]
        peers=[x for x in self._ordered_nodes if x.identity!=identity and not (set(x.conflict_keys)&set(n.conflict_keys))]
        return min(len(peers),32)
    def max_parallelism(self,completed=()):
        frontier=self.frontier(completed); used=set(); count=0
        for n in frontier:
            if set(n.conflict_keys)&used: continue
            used.update(n.conflict_keys); count+=1
        return count

def _conflicts(candidate,dependents_by_zone=None):
    keys={f"zone:{candidate.zone}",f"lane:{candidate.lane}"}
    if dependents_by_zone: keys.update(f"dependent-zone:{z}" for z in dependents_by_zone.get(candidate.zone,()))
    keys.update(f"dependency-zone:{z}" for z in candidate.dependency_zones)
    if candidate.path: keys.add(f"path:{candidate.path}")
    return tuple(sorted(keys))

def build_work_graph(model:RepositoryModel,*,limit:int=128)->WorkGraph:
    candidates=derive_work_candidates(model,limit=limit); best={}
    for c in candidates:
        if c.lane not in {"repository-health","architecture"}: continue
        if c.zone not in best or (-c.priority,c.identity)<(-best[c.zone].priority,best[c.zone].identity): best[c.zone]=c
    reverse={}
    for s in model.subsystems:
        for d in s.dependencies: reverse.setdefault(d,set()).add(s.name)
    dependents={z:tuple(sorted(v)) for z,v in reverse.items()}; nodes=[]
    for c in candidates:
        prerequisites=set(c.prerequisite_ids); higher=best.get(c.zone)
        if c.lane not in {"repository-health","architecture"} and higher and higher.priority>c.priority: prerequisites.add(higher.identity)
        nodes.append(WorkNode(c.identity,c.lane,c.zone,c.priority,c.objective,_conflicts(c,dependents),tuple(sorted(prerequisites)),c.evidence,c.verification_paths,"ready" if not prerequisites else "gated",c.decision_score,c.topology_confidence,c.blast_radius))
    return WorkGraph(tuple(nodes))
