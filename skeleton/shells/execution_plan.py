"""Immutable dependency-aware shell execution plans."""

from __future__ import annotations

from dataclasses import dataclass,field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.runner import ShellCommand

@dataclass(frozen=True)
class PlanStep:
    step_id:str
    command:ShellCommand
    depends_on:frozenset[str]=frozenset()
    continue_on_failure:bool=False

    def __post_init__(self)->None:
        if not self.step_id or len(self.step_id)>128:
            raise ValueError("invalid step_id")
        deps=frozenset(self.depends_on)
        if self.step_id in deps:
            raise ValueError("plan step cannot depend on itself")
        object.__setattr__(self,"depends_on",deps)

    def shape(self)->dict[str,object]:
        return {
            "step_id":self.step_id,
            "command":self.command.command,
            "args":list(self.command.args),
            "cwd":None if self.command.cwd is None else str(self.command.cwd),
            "env_keys":sorted(self.command.env),
            "stdin_bytes":None if self.command.stdin is None else len(self.command.stdin),
            "timeout":self.command.timeout,
            "allowed_returncodes":sorted(self.command.allowed_returncodes),
            "depends_on":sorted(self.depends_on),
            "continue_on_failure":self.continue_on_failure,
        }

@dataclass(frozen=True)
class ExecutionPlan:
    plan_id:str
    steps:tuple[PlanStep,...]
    metadata:Mapping[str,str]=field(default_factory=dict)

    def __post_init__(self)->None:
        if not self.plan_id or len(self.plan_id)>128:
            raise ValueError("invalid plan_id")
        steps=tuple(self.steps)
        if not steps:
            raise ValueError("execution plan requires at least one step")
        ids=[step.step_id for step in steps]
        if len(set(ids))!=len(ids):
            raise ValueError("duplicate execution plan step_id")
        known=set(ids)
        for step in steps:
            unknown=step.depends_on-known
            if unknown:
                raise ValueError(f"unknown plan dependency: {sorted(unknown)[0]}")
        metadata=dict(self.metadata)
        if len(metadata)>64:
            raise ValueError("too many plan metadata fields")
        object.__setattr__(self,"steps",steps)
        object.__setattr__(self,"metadata",MappingProxyType(metadata))
        self._validate_acyclic()

    def _validate_acyclic(self)->None:
        deps={step.step_id:set(step.depends_on) for step in self.steps}
        ready=[key for key,value in deps.items() if not value]
        visited=[]
        while ready:
            key=sorted(ready)[0]
            ready.remove(key)
            visited.append(key)
            for other in deps:
                if key in deps[other]:
                    deps[other].remove(key)
                    if not deps[other] and other not in visited and other not in ready:
                        ready.append(other)
        if len(visited)!=len(deps):
            raise ValueError("execution plan contains a dependency cycle")

    def topological_order(self)->tuple[PlanStep,...]:
        remaining={step.step_id:set(step.depends_on) for step in self.steps}
        by_id={step.step_id:step for step in self.steps}
        result=[]
        while remaining:
            ready=sorted(key for key,deps in remaining.items() if not deps)
            if not ready:
                raise RuntimeError("execution plan dependency cycle")
            for key in ready:
                result.append(by_id[key])
                del remaining[key]
                for deps in remaining.values():
                    deps.discard(key)
        return tuple(result)

    @property
    def fingerprint(self)->str:
        payload={
            "plan_id":self.plan_id,
            "steps":[step.shape() for step in self.steps],
            "metadata":dict(self.metadata),
        }
        raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(raw).hexdigest()
