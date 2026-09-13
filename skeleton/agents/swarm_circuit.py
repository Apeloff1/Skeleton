"""Circuit breaker policy for isolating repeatedly failing swarm workers."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from typing import Callable
class CircuitState(str,Enum): CLOSED="closed"; OPEN="open"; HALF_OPEN="half_open"
@dataclass(slots=True)
class Circuit:
    state:CircuitState=CircuitState.CLOSED; failures:int=0; opened_at:float|None=None; probes:int=0
class CircuitBreaker:
    def __init__(self,*,failure_threshold:int=5,recovery_seconds:float=30,clock:Callable[[],float]=monotonic):
        if failure_threshold<1 or recovery_seconds<=0: raise ValueError("invalid circuit breaker configuration")
        self.failure_threshold=failure_threshold; self.recovery_seconds=recovery_seconds; self.clock=clock; self._circuits={}
    def circuit(self,key:str)->Circuit: return self._circuits.setdefault(key,Circuit())
    def allow(self,key:str)->bool:
        c=self.circuit(key)
        if c.state is CircuitState.OPEN and c.opened_at is not None and self.clock()-c.opened_at>=self.recovery_seconds:
            c.state=CircuitState.HALF_OPEN; c.probes+=1; return True
        return c.state is not CircuitState.OPEN
    def success(self,key:str)->Circuit:
        c=self.circuit(key); c.state=CircuitState.CLOSED; c.failures=0; c.opened_at=None; return c
    def failure(self,key:str)->Circuit:
        c=self.circuit(key); c.failures+=1
        if c.state is CircuitState.HALF_OPEN or c.failures>=self.failure_threshold:
            c.state=CircuitState.OPEN; c.opened_at=self.clock()
        return c
    def snapshot(self)->dict[str,dict[str,object]]:
        return {k:{"state":v.state.value,"failures":v.failures,"opened_at":v.opened_at,"probes":v.probes} for k,v in sorted(self._circuits.items())}
