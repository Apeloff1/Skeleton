"""Closed allowlist for in-process, explicitly authorized, idempotent pure tools."""
from __future__ import annotations
from hashlib import sha256
from typing import Callable
from .contracts import Identity,SpineError,Conflict,canonical,identifier
from .policy import EffectGrant,require_effect

class ToolBoundary:
    def __init__(self,*,authorizing_key:bytes):
        if not isinstance(authorizing_key,bytes) or len(authorizing_key)<32:
            raise SpineError('independent tool authority key required')
        self._key=authorizing_key
        self._registry:dict[str,Callable[[dict],dict]]={}
    def register(self,name:str,handler:Callable[[dict],dict]):
        identifier(name,'tool')
        if name in self._registry or not callable(handler):raise SpineError('tool registration conflict')
        self._registry[name]=handler
    def invoke(self,identity:Identity,name:str,args:dict,grant:EffectGrant,signature:str):
        require_effect(identity,grant,name,args,authorizing_key=self._key,signature=signature)
        if name not in self._registry:raise Conflict('tool is not locally registered')
        canonical(args,ceiling=64_000)
        result=self._registry[name](dict(args))
        canonical(result,ceiling=262_144)
        return result
