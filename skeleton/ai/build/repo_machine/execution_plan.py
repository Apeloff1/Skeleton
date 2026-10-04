"""Closed-loop execution planning with reusable validated graph state."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from .model import RepositoryModel
from .workgraph import WorkGraph, build_work_graph

Phase=Literal["prepare","modify","verify","unlock"]; Outcome=Literal["success","failed","blocked","stale"]
@dataclass(frozen=True,slots=True)
class PlanStep:
    identity:str; phase:Phase; action:str; depends_on:tuple[str,...]=(); verification_paths:tuple[str,...]=(); work_identity:str=""
    def as_dict(self): return {"identity":self.identity,"phase":self.phase,"action":self.action,"depends_on":list(self.depends_on),"verification_paths":list(self.verification_paths),"work_identity":self.work_identity}
@dataclass(frozen=True,slots=True)
class ExecutionState:
    completed_steps:tuple[str,...]=(); failed_work:tuple[str,...]=(); verified_work:tuple[str,...]=(); released_work:tuple[str,...]=(); stale:bool=False
    def as_dict(self): return {"completed_steps":list(self.completed_steps),"failed_work":list(self.failed_work),"verified_work":list(self.verified_work),"released_work":list(self.released_work),"stale":self.stale}
@dataclass(frozen=True,slots=True)
class ExecutionPlan:
    repository_fingerprint:str; steps:tuple[PlanStep,...]; ready_work:tuple[str,...]; blocked_work:tuple[str,...]; state:ExecutionState=ExecutionState(); graph_fingerprint:str=""; parallel_batches:tuple[tuple[str,...],...]=()
    _steps_by_identity:dict[str,PlanStep]=field(init=False,repr=False,compare=False)
    def __post_init__(self):
        by={}
        for s in self.steps:
            if s.identity in by: raise ValueError(f"duplicate execution step: {s.identity}")
            by[s.identity]=s
        for s in self.steps:
            if any(d not in by for d in s.depends_on): raise ValueError(f"unknown step dependency for {s.identity}")
        object.__setattr__(self,"_steps_by_identity",by)
    @property
    def definition_fingerprint(self):
        p={"repository_fingerprint":self.repository_fingerprint,"steps":[s.as_dict() for s in self.steps],"ready_work":list(self.ready_work) ,"blocked_work":list(self.blocked_work),"parallel_batches":[list(b) for b in self.parallel_batches]}
        return hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps({"definition":self.definition_fingerprint,"state":self.state.as_dict()},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    def as_dict(self): return {"repository_fingerprint":self.repository_fingerprint,"plan_fingerprint":self.fingerprint,"definition_fingerprint":self.definition_fingerprint,"steps":[s.as_dict() for s in self.steps],"ready_work":list(self.ready_work),"blocked_work":list(self.blocked_work),"state":self.state.as_dict(),"graph_fingerprint":self.graph_fingerprint,"parallel_batches":[list(b) for b in self.parallel_batches]}

def _stale_plan(plan,completed,failed,verified,released):
    return ExecutionPlan(plan.repository_fingerprint,plan.steps,(),plan.blocked_work,ExecutionState(tuple(sorted(completed)),tuple(sorted(failed)),tuple(sorted(verified)),tuple(sorted(released)),True),plan.graph_fingerprint,plan.parallel_batches)

def advance_execution(plan,*,step_identity:str,outcome:Outcome,repository_fingerprint:str,expected_plan_fingerprint:str|None=None):
    if expected_plan_fingerprint is not None and expected_plan_fingerprint!=plan.fingerprint: raise ValueError("execution plan fingerprint mismatch")
    if repository_fingerprint!=plan.repository_fingerprint: return _stale_plan(plan,set(plan.state.completed_steps),set(plan.state.failed_work),set(plan.state.verified_work),set(plan.state.released_work))
    step=plan._steps_by_identity.get(step_identity)
    if step is None: raise ValueError("unknown execution step")
    completed=set(plan.state.completed_steps); failed=set(plan.state.failed_work); verified=set(plan.state.verified_work); released=set(plan.state.released_work)
    if step.identity in completed: raise ValueError("execution step already completed")
    if any(d not in completed for d in step.depends_on): raise ValueError("execution step prerequisites are incomplete")
    if outcome=="success":
        completed.add(step.identity)
        if step.phase=="verify": verified.add(step.work_identity)
        elif step.phase=="unlock":
            if step.work_identity not in verified: raise ValueError("work must be verified before unlock")
            released.add(step.work_identity); failed.discard(step.work_identity)
    elif outcome=="failed": failed.add(step.work_identity); verified.discard(step.work_identity); released.discard(step.work_identity)
    elif outcome=="stale": return _stale_plan(plan,completed,failed,verified,released)
    elif outcome=="blocked": return plan
    return ExecutionPlan(plan.repository_fingerprint,plan.steps,plan.ready_work,plan.blocked_work,ExecutionState(tuple(sorted(completed)),tuple(sorted(failed)),tuple(sorted(verified)),tuple(sorted(released)),False),plan.graph_fingerprint,plan.parallel_batches)

def build_execution_plan(model:RepositoryModel,*,completed:Iterable[str]=(),active_conflicts:Iterable[str]=(),limit:int=8,state:ExecutionState|None=None,retry_failed:bool=False,graph:WorkGraph|None=None):
    graph=graph or build_work_graph(model,limit=max(limit,32)); inherited=state or ExecutionState(); completed_set=set(completed)|set(inherited.released_work)
    ready=graph.ready(completed_set,active_conflicts,limit=limit); failed=set(inherited.failed_work)
    if not retry_failed: ready=tuple(n for n in ready if n.identity not in failed)
    ready_ids={n.identity for n in ready}; steps=[]
    for n in ready:
        prepare,modify,verify,unlock=(f"{n.identity}:{p}" for p in ("prepare","modify","verify","unlock"))
        steps.extend((PlanStep(prepare,"prepare",f"Inspect evidence and establish the bounded change scope for {n.identity}.",work_identity=n.identity),
                      PlanStep(modify,"modify",n.objective,(prepare,),work_identity=n.identity),
                      PlanStep(verify,"verify","Run the smallest relevant verification surface before considering the work complete.",(modify,),n.verification_paths,n.identity),
                      PlanStep(unlock,"unlock","Release the verified work and recompute downstream readiness.",(verify,),work_identity=n.identity)))
    blocked=tuple(n.identity for n in graph.ordered_nodes if n.identity not in ready_ids and n.identity not in completed_set)
    batches=tuple(tuple(group) for group in graph.safe_parallel_groups(completed_set,limit=min(8,limit)))
    return ExecutionPlan(model.fingerprint,tuple(steps),tuple(n.identity for n in ready),blocked,inherited,graph.fingerprint,batches)

def replan_execution(model,previous,*,active_conflicts=(),limit=8,retry_failed=False,graph=None):
    return build_execution_plan(model,active_conflicts=active_conflicts,limit=limit,state=previous.state,retry_failed=retry_failed,graph=graph)
__all__=["ExecutionPlan","ExecutionState","Outcome","Phase","PlanStep","advance_execution","build_execution_plan","replan_execution"]
