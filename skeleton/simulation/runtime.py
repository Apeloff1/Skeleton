"""Deterministic, non-authoritative world-model simulation contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, math
from types import MappingProxyType
from typing import Mapping, Protocol

MAX_STATE_KEYS=512
MAX_ASSUMPTIONS=128
MAX_STEPS=4096

class SimulationError(ValueError): pass

def _digest(v:object)->str:
    return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def _finite(v:float)->float:
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): raise SimulationError("uncertainty must be finite")
    v=float(v)
    if not 0.0<=v<=1.0: raise SimulationError("uncertainty outside [0,1]")
    return v

@dataclass(frozen=True)
class AssumptionSet:
    values: Mapping[str,str]
    uncertainty: float
    def __post_init__(self):
        if not isinstance(self.values,Mapping) or len(self.values)>MAX_ASSUMPTIONS: raise SimulationError("assumption budget exceeded")
        clean={}
        for k,v in self.values.items():
            if not isinstance(k,str) or not k or len(k)>128 or not isinstance(v,str) or len(v)>1024: raise SimulationError("invalid assumption")
            clean[k]=v
        object.__setattr__(self,"values",MappingProxyType(dict(sorted(clean.items()))))
        object.__setattr__(self,"uncertainty",_finite(self.uncertainty))
    @property
    def digest(self)->str: return _digest({"values":dict(self.values),"uncertainty":self.uncertainty})

@dataclass(frozen=True)
class WorldState:
    values: Mapping[str,str]
    uncertainty: float=0.0
    def __post_init__(self):
        if not isinstance(self.values,Mapping) or len(self.values)>MAX_STATE_KEYS: raise SimulationError("state budget exceeded")
        clean={}
        for k,v in self.values.items():
            if not isinstance(k,str) or not k or len(k)>128 or not isinstance(v,str) or len(v)>4096: raise SimulationError("invalid state")
            clean[k]=v
        object.__setattr__(self,"values",MappingProxyType(dict(sorted(clean.items()))))
        object.__setattr__(self,"uncertainty",_finite(self.uncertainty))
    @property
    def digest(self)->str: return _digest({"values":dict(self.values),"uncertainty":self.uncertainty})

@dataclass(frozen=True)
class Transition:
    values: Mapping[str,str]
    uncertainty: float
    def __post_init__(self):
        WorldState(self.values,self.uncertainty)

class EnvironmentAdapter(Protocol):
    def transition(self,state:WorldState,action:str,assumptions:AssumptionSet)->Transition: ...

@dataclass(frozen=True)
class SimulationStep:
    ordinal:int; prior_state_digest:str; action:str; assumption_digest:str; result_state_digest:str; uncertainty:float
    @property
    def digest(self)->str: return _digest(self.__dict__)

@dataclass(frozen=True)
class SimulationResult:
    initial_state_digest:str; final_state:WorldState; steps:tuple[SimulationStep,...]; authority_scope:str="simulation-evidence-only"
    def __post_init__(self):
        if self.authority_scope!="simulation-evidence-only": raise SimulationError("simulation cannot grant real-world authority")
    @property
    def result_digest(self)->str: return _digest({"initial":self.initial_state_digest,"final":self.final_state.digest,"steps":[x.digest for x in self.steps],"authority":self.authority_scope})

def simulate(adapter:EnvironmentAdapter,initial:WorldState,actions:tuple[str,...],assumptions:AssumptionSet)->SimulationResult:
    if not isinstance(initial,WorldState) or not isinstance(assumptions,AssumptionSet): raise SimulationError("typed inputs required")
    if not isinstance(actions,tuple) or len(actions)>MAX_STEPS: raise SimulationError("step budget exceeded")
    state=initial; steps=[]
    for i,action in enumerate(actions):
        if not isinstance(action,str) or not action or len(action)>1024: raise SimulationError("invalid action")
        t=adapter.transition(state,action,assumptions)
        if not isinstance(t,Transition): raise SimulationError("adapter returned invalid transition")
        propagated=1.0-(1.0-state.uncertainty)*(1.0-assumptions.uncertainty)*(1.0-_finite(t.uncertainty))
        nxt=WorldState(t.values,propagated)
        steps.append(SimulationStep(i,state.digest,action,assumptions.digest,nxt.digest,nxt.uncertainty)); state=nxt
    return SimulationResult(initial.digest,state,tuple(steps))
