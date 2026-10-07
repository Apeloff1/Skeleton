"""Conflict-aware work graph with dependency, frontier, critical-path, and parallelism intelligence."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
from typing import Iterable
from .model import RepositoryModel
from .planner import WorkCandidate, derive_work_candidates

@dataclass(frozen=True, slots=True)
class WorkNode:
    identity:str; lane:str; zone:str; priority:int; objective:str; conflict_keys:tuple[str,...]; prerequisites:tuple[str,...]; evidence:tuple[str,...]
    verification_paths:tuple[str,...]=(); readiness:str="ready"; decision_score:int=0; topology_confidence:int=0; blast_radius:int=0
    critical_path_depth:int=0; unlock_potential:int=0; strategic_score:int=0
    def as_dict(self)->dict[str,object]:
        return {"identity":self.identity,"lane":self.lane,"zone":self.zone,"priority":self.priority,"objective":self.objective,"conflict_keys":list(self.conflict_keys),"prerequisites":list(self.prerequisites),"evidence":list(self.evidence),"verification_paths":list(self.verification_paths),"readiness":self.readiness,"decision_score":self.decision_score,"topology_confidence":self.topology_confidence,"blast_radius":self.blast_radius,"critical_path_depth":self.critical_path_depth,"unlock_potential":self.unlock_potential,"strategic_score":self.strategic_score}

@dataclass(frozen=True, slots=True)
class WorkGraph:
    nodes:tuple[WorkNode,...]
    _ordered_nodes:tuple[WorkNode,...]=field(init=False,repr=False,compare=False); _by_identity:dict[str,WorkNode]=field(init=False,repr=False,compare=False)
    _depth:dict[str,int]=field(init=False,repr=False,compare=False); _descendants:dict[str,frozenset[str]]=field(init=False,repr=False,compare=False); _fingerprint:str=field(init=False,repr=False,compare=False)
    def __post_init__(self)->None:
        ordered=tuple(sorted(self.nodes,key=lambda n:(-n.priority,n.identity))); ids={n.identity for n in ordered}
        if len(ids)!=len(ordered): raise ValueError("work graph contains duplicate identities")
        by={n.identity:n for n in ordered}
        for n in ordered:
            if any(p not in by for p in n.prerequisites): raise ValueError(f"work graph has unknown prerequisites for {n.identity}")
        visiting=set(); visited=set(); depth={}; descendants={i:set() for i in by}
        def visit(i):
            if i in visiting: raise ValueError(f"work graph contains prerequisite cycle at {i}")
            if i in visited:return depth[i]
            visiting.add(i); d=0
            for p in by[i].prerequisites:d=max(d,visit(p)+1); descendants[p].add(i); descendants[p].update(descendants[i])
            visiting.remove(i); visited.add(i); depth[i]=d; return d
        for i in by:visit(i)
        max_depth=max(depth.values(),default=0); enriched=[]
        for n in ordered:
            unlock=len(descendants[n.identity]); strategic=min(100,max(0,n.decision_score+min(25,unlock*5)+min(15,depth[n.identity]*3)+min(10,n.blast_radius*2)+min(10,n.topology_confidence//10)+(10 if max_depth and depth[n.identity]==max_depth else 0)))
            enriched.append(WorkNode(n.identity,n.lane,n.zone,n.priority,n.objective,n.conflict_keys,n.prerequisites,n.evidence,n.verification_paths,n.readiness,n.decision_score,n.topology_confidence,n.blast_radius,depth[n.identity],unlock,strategic))
        object.__setattr__(self,"_ordered_nodes",tuple(enriched)); object.__setattr__(self,"_by_identity",{n.identity:n for n in enriched}); object.__setattr__(self,"_depth",depth); object.__setattr__(self,"_descendants",{k:frozenset(v) for k,v in descendants.items()})
        payload="|".join(f"{n.identity}:{n.priority}:{n.strategic_score}:{n.prerequisites}:{n.conflict_keys}" for n in enriched); object.__setattr__(self,"_fingerprint",hashlib.sha256(payload.encode()).hexdigest())
    @property
    def ordered_nodes(self): return self._ordered_nodes
    def node(self,identity):
        try:return self._by_identity[identity]
        except KeyError as exc:raise ValueError(f"unknown work identity: {identity}") from exc
    @property
    def fingerprint(self):return self._fingerprint
    @property
    def critical_depth(self):return max(self._depth.values(),default=0)
    def as_dict(self):
        return {"fingerprint":self.fingerprint,"nodes":[n.as_dict() for n in self._ordered_nodes],"frontier":[n.identity for n in self.frontier()],"critical_path_depth":self.critical_depth,"max_parallelism":self.max_parallelism(),"bottleneck":self.bottleneck(),"coordination_pressure":self.pressure(),"strategic_value":self.strategic_value(),"bridge_candidates":list(self.bridge_candidates()),"parallel_batch_surface":list(self.parallel_batch_surface(limit=4)),"counterfactual_surface":list(self.counterfactual_surface(limit=8))}
    def frontier(self,completed=()):
        done=set(completed); return tuple(sorted((n for n in self._ordered_nodes if n.identity not in done and all(p in done for p in n.prerequisites)),key=lambda n:(-n.strategic_score,-n.priority,n.identity)))
    def ready(self,completed=(),active_conflicts=(),*,limit=8):
        done=set(completed); unknown=done-set(self._by_identity)
        if unknown:raise ValueError("completed contains unknown work identities")
        conflicts=set(active_conflicts); selected=[]
        for n in self.frontier(done):
            if any(k in conflicts for k in n.conflict_keys):continue
            selected.append(n); conflicts.update(n.conflict_keys)
            if len(selected)>=limit:break
        return tuple(selected)
    def blocked(self,completed=()):
        done=set(completed); return tuple(n for n in self._ordered_nodes if n.identity not in done and any(p not in done for p in n.prerequisites))
    def unlock_potential(self,identity):return len(self._descendants[self.node(identity).identity])
    def critical_path(self):
        if not self._ordered_nodes:return ()
        terminal=max(self._ordered_nodes,key=lambda n:(self._depth[n.identity],n.strategic_score,n.priority,n.identity)); path=[terminal]
        while path[-1].prerequisites:path.append(max((self._by_identity[p] for p in path[-1].prerequisites),key=lambda n:(self._depth[n.identity],n.strategic_score,n.priority,n.identity)))
        return tuple(reversed(path))
    def bottleneck(self,completed=()):
        frontier=self.frontier(completed)
        if not frontier:return None
        return max(frontier,key=lambda n:(len(self._descendants[n.identity]),self._depth[n.identity],n.strategic_score,n.priority,n.identity)).identity
    def parallelism_hint(self,identity):
        n=self.node(identity); peers=[x for x in self._ordered_nodes if x.identity!=identity and not (set(x.conflict_keys)&set(n.conflict_keys))]
        return min(len(peers),32)
    def max_parallelism(self,completed=()):
        frontier=self.frontier(completed); used=set(); count=0
        for n in frontier:
            if set(n.conflict_keys)&used:continue
            used.update(n.conflict_keys);count+=1
        return count
    def node_pressure(self,identity):return self._pressure(self.node(identity))
    def downstream_value(self,identity):
        node=self.node(identity);return min(100,node.strategic_score+sum(min(10,self._by_identity[d].strategic_score//10) for d in self._descendants[identity]))
    def conflict_density(self,identity):
        node=self.node(identity);keys=set(node.conflict_keys)
        if not keys:return 0
        return min(100,sum(1 for other in self._ordered_nodes if other.identity!=identity and keys.intersection(other.conflict_keys))*4)
    def safe_parallel_groups(self,completed=(),*,limit=8):
        if isinstance(limit,bool) or not isinstance(limit,int) or limit<1:raise ValueError("limit must be positive")
        remaining=list(self.frontier(completed));groups=[]
        while remaining and len(groups)<limit:
            group=[];used=set();rest=[]
            for n in remaining:
                keys=set(n.conflict_keys)
                if not keys.intersection(used):group.append(n.identity);used.update(keys)
                else:rest.append(n)
            if not group:break
            groups.append(tuple(group));remaining=rest
        return tuple(groups)
    def parallel_batch_surface(self,completed=(),*,limit=8):
        """Score bounded conflict-free batches by value, risk and verification coverage."""
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=8:raise ValueError("limit must be in [1,8]")
        rows=[]
        for index,group in enumerate(self.safe_parallel_groups(completed,limit=limit),1):
            nodes=[self.node(i) for i in group]
            influence=sum(self.risk_adjusted_influence(n.identity) for n in nodes)//max(1,len(nodes))
            unlock=sum(self.counterfactual_unlock(n.identity,completed) for n in nodes)
            verification=sum(1 for n in nodes if n.verification_paths)
            pressure=max((self.node_pressure(n.identity) for n in nodes),default=0)
            conflict_density=sum(self.conflict_density(n.identity) for n in nodes)//max(1,len(nodes))
            decision_margin=sum(self.decision_margin(n.identity,completed) for n in nodes)//max(1,len(nodes))
            rows.append({"batch":index,"identities":list(group),"size":len(group),"risk_adjusted_influence":min(100,influence),"counterfactual_unlock":min(100,unlock),"verification_coverage":verification*100//max(1,len(group)),"pressure":pressure,"conflict_density":min(100,conflict_density),"decision_margin":min(100,decision_margin)})
        return tuple(rows)
    def influence(self,identity):
        node=self.node(identity);return min(100,self.downstream_value(identity)*2//3+self.conflict_density(identity)//2+min(25,node.blast_radius*5))
    def strategic_value(self,completed=()):
        frontier=self.frontier(completed);return min(100,sum(self.influence(n.identity) for n in frontier[:32])//max(1,len(frontier)))
    def risk_adjusted_influence(self,identity):
        node=self.node(identity);confidence=max(1,node.topology_confidence);penalty=self.conflict_density(identity)//3+self.node_pressure(identity)//5
        return min(100,max(0,self.influence(identity)*confidence//100-penalty))
    def verification_efficiency(self,identity):
        node=self.node(identity);return min(100,(self.downstream_value(identity)*10)//max(1,len(node.verification_paths)))
    def decision_margin(self,identity,completed=()):
        target=self.risk_adjusted_influence(identity);rivals=[self.risk_adjusted_influence(n.identity) for n in self.frontier(completed) if n.identity!=identity]
        return max(0,target-max(rivals,default=0))
    def counterfactual_unlock(self,identity,completed=()):
        done=set(completed);done.add(self.node(identity).identity);return max(0,self.pressure(completed)-self.pressure(done))
    def decision_surface(self,completed=(),*,limit=16):
        if isinstance(limit,bool) or not isinstance(limit,int) or limit<1:raise ValueError("limit must be positive")
        rows=[]
        for n in self.frontier(completed)[:max(1,limit)]:
            rows.append({"identity":n.identity,"risk_adjusted_influence":self.risk_adjusted_influence(n.identity),"verification_efficiency":self.verification_efficiency(n.identity),"counterfactual_unlock":self.counterfactual_unlock(n.identity,completed),"decision_margin":self.decision_margin(n.identity,completed),"pressure":self.node_pressure(n.identity),"downstream_value":self.downstream_value(n.identity)})
        return tuple(rows)
    def counterfactual_surface(self,completed=(),*,limit=16):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=64:raise ValueError("limit must be in [1,64]")
        done=set(completed); baseline=self.pressure(done); rows=[]; frontier=self.frontier(done)
        for n in frontier[:limit]:
            hypothetical=done|{n.identity}; after=self.pressure(hypothetical)
            before_ready={x.identity for x in frontier}; after_ready={x.identity for x in self.frontier(hypothetical)}
            newly=tuple(sorted(after_ready-before_ready))
            rows.append({"identity":n.identity,"pressure_reduction":max(0,baseline-after),"projected_pressure":after,"newly_unblocked":list(newly[:16]),"newly_unblocked_count":len(newly),"risk_adjusted_influence":self.risk_adjusted_influence(n.identity),"strategic_value":self.influence(n.identity)})
        rows.sort(key=lambda r:(-r["pressure_reduction"],-r["newly_unblocked_count"],-r["risk_adjusted_influence"],-r["strategic_value"],r["identity"]))
        return tuple(rows[:limit])
    def bridge_candidates(self,*,limit=16):
        scored=[]
        for n in self._ordered_nodes:
            descendants=self._descendants[n.identity]
            if descendants:
                covered=sum(1 for d in descendants if n.identity in self._by_identity[d].prerequisites);scored.append((min(100,len(descendants)*4+covered*8+self._depth[n.identity]*3),n.identity))
        scored.sort(reverse=True);return tuple(identity for _,identity in scored[:max(0,limit)])
    def pressure(self,completed=()):
        frontier=self.frontier(completed)
        if not frontier:return 0
        return min(100,max(self._pressure(n) for n in frontier))
    @staticmethod
    def _pressure(node):return min(100,node.unlock_potential*6+node.blast_radius*3+len(node.conflict_keys)*2+(20 if node.critical_path_depth else 0))

def _conflicts(candidate,dependents_by_zone=None):
    keys={f"zone:{candidate.zone}",f"lane:{candidate.lane}"}
    if dependents_by_zone:keys.update(f"dependent-zone:{z}" for z in dependents_by_zone.get(candidate.zone,()))
    keys.update(f"dependency-zone:{z}" for z in candidate.dependency_zones)
    if candidate.path:keys.add(f"path:{candidate.path}")
    return tuple(sorted(keys))
def build_work_graph(model:RepositoryModel,*,limit=128):
    candidates=derive_work_candidates(model,limit=limit);best={}
    for c in candidates:
        if c.lane not in {"repository-health","architecture"}:continue
        if c.zone not in best or (-c.priority,c.identity)<(-best[c.zone].priority,best[c.zone].identity):best[c.zone]=c
    reverse={}
    for s in model.subsystems:
        for d in s.dependencies:reverse.setdefault(d,set()).add(s.name)
    dependents={z:tuple(sorted(v)) for z,v in reverse.items()};nodes=[]
    for c in candidates:
        prerequisites=set(c.prerequisite_ids);higher=best.get(c.zone)
        if c.lane not in {"repository-health","architecture"} and higher and higher.priority>c.priority:prerequisites.add(higher.identity)
        nodes.append(WorkNode(c.identity,c.lane,c.zone,c.priority,c.objective,_conflicts(c,dependents),tuple(sorted(prerequisites)),c.evidence,c.verification_paths,"ready" if not prerequisites else "gated",c.decision_score,c.topology_confidence,c.blast_radius))
    return WorkGraph(tuple(nodes))
