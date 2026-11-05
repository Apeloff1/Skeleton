"""Finite upper bounds shared by planner, store, model, and tools."""
from dataclasses import dataclass
from .canonical import uint
@dataclass(frozen=True,slots=True)
class Limits:
    steps:int=256
    dependencies:int=32
    input_bytes:int=32768
    result_bytes:int=131072
    attempts:int=1
    active_jobs:int=16
    events:int=8192
    plan_bytes:int=262144
    model_tokens:int=512
    max_idle_ms:int=30000
    def __post_init__(self):
        for name,ceiling in [('steps',1024),('dependencies',64),('input_bytes',1048576),('result_bytes',1048576),('attempts',1),('active_jobs',256),('events',65536),('plan_bytes',2097152),('model_tokens',8192),('max_idle_ms',600000)]:
            uint(getattr(self,name),name,1,ceiling)
    def record(self):return {k:getattr(self,k) for k in self.__dataclass_fields__}
