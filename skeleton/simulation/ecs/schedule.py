"""Deterministic dependency planning and conflict-free execution batches."""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping
from .canonical import digest
from .errors import ScheduleCycleError,ScheduleError,SystemConflictError,SystemNotFoundError
MAX_SYSTEMS=10_000;MAX_DEPENDENCIES=100_000
class SystemPhase(IntEnum):PRE=10;UPDATE=20;POST=30
@dataclass(frozen=True)
class SystemSpec:
    system_id:str;phase:SystemPhase=SystemPhase.UPDATE;reads:tuple[str,...]=();writes:tuple[str,...]=();after:tuple[str,...]=();before:tuple[str,...]=();enabled:bool=True
    def __post_init__(self):
        if not isinstance(self.system_id,str) or not self.system_id:raise ScheduleError("system id required")
        if not isinstance(self.phase,SystemPhase):object.__setattr__(self,"phase",SystemPhase(self.phase))
        for name in ("reads","writes","after","before"):object.__setattr__(self,name,tuple(sorted(set(getattr(self,name)))))
        if set(self.reads)&set(self.writes):object.__setattr__(self,"reads",tuple(x for x in self.reads if x not in self.writes))
@dataclass(frozen=True)
class ExecutionBatch:index:int;system_ids:tuple[str,...]
@dataclass(frozen=True)
class ExecutionPlan:ordered_system_ids:tuple[str,...];batches:tuple[ExecutionBatch,...];dependencies:Mapping[str,tuple[str,...]];fingerprint:str
def conflicts(a:SystemSpec,b:SystemSpec)->bool:
    aw,bw,ar,br=set(a.writes),set(b.writes),set(a.reads),set(b.reads);return bool((aw&bw)|(aw&br)|(bw&ar))
class SystemGraph:
    def __init__(self):self._systems={}
    def register(self,spec:SystemSpec):
        if len(self._systems)>=MAX_SYSTEMS and spec.system_id not in self._systems:raise ScheduleError("system bound exceeded")
        prior=self._systems.get(spec.system_id)
        if prior is not None and prior!=spec:raise SystemConflictError("system id conflict",context={"system_id":spec.system_id})
        self._systems[spec.system_id]=spec;return spec
    def get(self,system_id):
        if system_id not in self._systems:raise SystemNotFoundError("system not found",context={"system_id":system_id})
        return self._systems[system_id]
    def system_ids(self):return tuple(sorted(self._systems))
    def _dependencies(self):
        deps={sid:set() for sid in self._systems};edges=0
        for sid,spec in self._systems.items():
            for dep in spec.after:
                if dep not in self._systems:raise SystemNotFoundError("after dependency not found",context={"system_id":sid,"dependency":dep})
                deps[sid].add(dep);edges+=1
            for target in spec.before:
                if target not in self._systems:raise SystemNotFoundError("before dependency not found",context={"system_id":sid,"dependency":target})
                deps[target].add(sid);edges+=1
        ids=sorted(self._systems)
        for i,a_id in enumerate(ids):
            a=self._systems[a_id]
            for b_id in ids[i+1:]:
                b=self._systems[b_id]
                if a.phase<b.phase:deps[b_id].add(a_id)
                elif b.phase<a.phase:deps[a_id].add(b_id)
        if edges>MAX_DEPENDENCIES:raise ScheduleError("dependency bound exceeded")
        return deps
    def plan(self):
        deps=self._dependencies();remaining={k:set(v) for k,v in deps.items()};ordered=[];batches=[]
        while remaining:
            ready=sorted([sid for sid,d in remaining.items() if not d],key=lambda sid:(self._systems[sid].phase,sid))
            if not ready:raise ScheduleCycleError("system dependency cycle",context={"remaining":sorted(remaining)})
            batch=[]
            for sid in ready:
                if not self._systems[sid].enabled:continue
                if any(conflicts(self._systems[sid],self._systems[other]) for other in batch):continue
                batch.append(sid)
            if not batch:batch=[ready[0]]
            batches.append(ExecutionBatch(len(batches),tuple(batch)))
            for sid in batch:ordered.append(sid);remaining.pop(sid)
            for d in remaining.values():d.difference_update(batch)
        frozen={k:tuple(sorted(v)) for k,v in sorted(deps.items())};fp=digest({"domain":"skeleton.simulation.ecs.execution_plan.v1","ordered":ordered,"batches":[b.system_ids for b in batches],"dependencies":frozen})
        return ExecutionPlan(tuple(ordered),tuple(batches),frozen,fp)
