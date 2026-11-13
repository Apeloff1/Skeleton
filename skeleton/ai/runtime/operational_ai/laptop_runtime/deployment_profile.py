"""Immutable operator-set laptop resource profile; no implicit capacity escalation."""
from __future__ import annotations
from dataclasses import dataclass,replace
from .contracts import refuse

@dataclass(frozen=True,slots=True)
class LaptopProfile:
    n_ctx:int=2048
    max_new_tokens:int=256
    threads:int=4
    gpu_layers:int=0
    capacity_slots:int=1
    capacity_budget_bytes:int=8000000000
    inference_ms:int=90000

    def __post_init__(self):
        bounds={"n_ctx":(128,131072),"max_new_tokens":(1,8192),
                "threads":(1,64),"gpu_layers":(0,128),
                "capacity_slots":(1,64),
                "capacity_budget_bytes":(1,20000000000),
                "inference_ms":(100,600000)}
        for key,(lo,hi) in bounds.items():
            value=getattr(self,key)
            if type(value) is not int or not lo<=value<=hi:
                refuse("invalid laptop resource "+key)
        if self.max_new_tokens>=self.n_ctx:
            refuse("generated token allowance exceeds context")

    def attenuate(self,**fields):
        for key,value in fields.items():
            if key not in self.__dataclass_fields__ or type(value) is not int:
                refuse("unknown resource attenuation")
            if value>getattr(self,key):
                refuse("resource policy may not silently escalate")
        return replace(self,**fields)

    def to_record(self):
        return {k:getattr(self,k) for k in self.__dataclass_fields__}
