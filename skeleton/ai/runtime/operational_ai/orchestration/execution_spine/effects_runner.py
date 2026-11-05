"""Separately authenticated effect dispatch with durable ambiguity fencing."""
from __future__ import annotations
from .contracts import Identity,Conflict
from .database import SpineDatabase
from .tools import ToolBoundary
from .policy import EffectGrant
from . import effects

class EffectRunner:
    def __init__(self,db:SpineDatabase,boundary:ToolBoundary):
        self.db=db;self.boundary=boundary
    def execute(self,identity:Identity,session:str,grant:EffectGrant,signature:str,name:str,args:dict):
        # Independently verify permission before writing attempt. This call is
        # made by a trusted caller, never triggered by generated model text.
        from .policy import require_effect
        require_effect(identity,grant,name,args,authorizing_key=self.boundary._key,signature=signature)
        with self.db.transaction() as conn:
            effects.prepare(conn,identity,session,grant,signature,name,args,key=self.boundary._key)
        # If the process crashes here, state stays "attempting" and no automatic
        # replay is possible. Operator must determine external side-effect result.
        result=self.boundary.invoke(identity,name,args,grant,signature)
        with self.db.transaction() as conn:
            receipt=effects.finalize(conn,identity,session,grant,result)
        return {'result':result,'receipt':receipt}
