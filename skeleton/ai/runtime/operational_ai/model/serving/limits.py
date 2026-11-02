"""Physical memory and context policy for inference profiles."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import ServingError

@dataclass(frozen=True,slots=True)
class Capacity:
    physical_memory:int
    model_memory:int
    reserved_memory:int
    context_limit:int
    max_parallel:int

    def __post_init__(self)->None:
        values=(self.physical_memory,self.model_memory,self.reserved_memory,self.context_limit,self.max_parallel)
        if any(type(v) is not int or v<=0 for v in values):raise ServingError('capacity fields must be positive integers')
        if self.model_memory+self.reserved_memory>self.physical_memory:
            raise ServingError('model exceeds available physical memory')
        if not 128<=self.context_limit<=262144 or self.max_parallel>64:
            raise ServingError('unsupported context or worker capacity')

    def can_admit(self,requested_context:int,estimated_worker_memory:int,live:int)->bool:
        if any(type(x) is not int or x<0 for x in (requested_context,estimated_worker_memory,live)):
            return False
        return (requested_context<=self.context_limit and live<self.max_parallel and
            self.model_memory+self.reserved_memory+(live+1)*estimated_worker_memory<=self.physical_memory)
