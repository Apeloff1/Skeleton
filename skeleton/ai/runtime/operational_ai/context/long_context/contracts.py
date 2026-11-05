"""Typed trust-labeled context elements with explicit immutable identity."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,re

class ContextError(RuntimeError):pass

ID=re.compile(r'^[A-Za-z0-9_-]{1,128}$')
TRUST={'system','user','assistant','retrieved','tool_result'}

@dataclass(frozen=True,slots=True)
class Span:
    span_id:str
    trust:str
    text:str
    revision:int
    digest:str

    def __post_init__(self):
        if not ID.fullmatch(self.span_id):raise ContextError('invalid context span identifier')
        if self.trust not in TRUST:raise ContextError('unrecognized context authority')
        if type(self.revision) is not int or self.revision<0:raise ContextError('invalid span revision')
        if not isinstance(self.text,str) or len(self.text.encode('utf8'))>2_097_152:
            raise ContextError('context span exceeds text capacity')
        if hashlib.sha256(self.text.encode('utf8')).hexdigest()!=self.digest:
            raise ContextError('span digest mismatch')

    @classmethod
    def from_text(cls,name:str,trust:str,body:str,revision:int=0):
        return cls(name,trust,body,revision,hashlib.sha256(body.encode('utf8')).hexdigest())
