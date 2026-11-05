"""Versioned operation trace with content-free checkpoint identifiers."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .contracts import Identity,identifier,hexdigest,canonical,SpineError
@dataclass(frozen=True,slots=True)
class Trace:
    schema:str
    principal:str
    session:str
    request_id:str
    input_sha256:str
    output_sha256:str
    revision:int
    def __post_init__(self):
        if self.schema!='spine.trace.v1':raise SpineError('invalid trace schema')
        for field in ('principal','input_sha256','output_sha256'):hexdigest(getattr(self,field))
        identifier(self.session);identifier(self.request_id)
        if type(self.revision)is not int or self.revision<1:raise SpineError('invalid trace revision')
    def serialize(self)->bytes:return canonical({name:getattr(self,name) for name in self.__dataclass_fields__},ceiling=4096)
