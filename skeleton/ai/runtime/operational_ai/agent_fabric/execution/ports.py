"""Strictly injected ports; no external effects without explicit authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from ..core.errors import Invalid,Unauthorized
from ..core.canonical import text,canonical,hex_digest
class ModelPort(Protocol):
    def complete(self,*,session:str,request_id:str,prompt:str,seed:int=0,temperature:float=.8)->dict:...
class ToolPort(Protocol):
    def execute(self,resource:str,operation:str,arguments:dict)->dict:...
class ReadPort(Protocol):
    def read(self,*,instruction:str,owner:str)->dict:...
class ReviewPort(Protocol):
    def request_approval(self,plan_id:str,step_id:str,instruction:str)->dict:...
@dataclass(frozen=True,slots=True)
class Ports:
    model:ModelPort
    tool:ToolPort|None=None
    reader:ReadPort|None=None
    reviewer:ReviewPort|None=None
    operator_key:bytes|None=None
    def __post_init__(self):
        if not callable(getattr(self.model,'complete',None)):raise Invalid('live model port required')
        if self.tool is not None and not callable(getattr(self.tool,'execute',None)):raise Invalid('tool callable required')
        if self.reader is not None and not callable(getattr(self.reader,'read',None)):raise Invalid('reader callable required')
        if self.reviewer is not None and not callable(getattr(self.reviewer,'request_approval',None)):raise Invalid('review callable required')
        if self.operator_key is not None and (not isinstance(self.operator_key,bytes) or len(self.operator_key)<32):
            raise Invalid('operator key is not strong')
