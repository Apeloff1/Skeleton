"""Typed, bounded tool protocol and immutable command envelopes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Literal
import re,hashlib,json
_ID=re.compile(r'^[a-z][a-z0-9_]{1,63}$')
_SCOPE=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')

class ToolError(ValueError):pass

@dataclass(frozen=True,slots=True)
class ToolArgument:
    name:str
    type:str
    required:bool=True
    max_length:int=4096
    def __post_init__(self):
        if not _ID.fullmatch(self.name) or self.type not in ('str','int','bool','list[str]'):
            raise ToolError('invalid tool argument contract')
        if type(self.max_length) is not int or not 1<=self.max_length<=65536:
            raise ToolError('invalid argument size ceiling')

@dataclass(frozen=True,slots=True)
class ToolSpec:
    name:str
    version:int
    arguments:tuple[ToolArgument,...]
    risk:Literal['read','write','external','privileged']
    scope:str
    max_output_bytes:int=65536
    timeout_ms:int=10000
    idempotent:bool=False
    def __post_init__(self):
        if not _ID.fullmatch(self.name) or type(self.version) is not int or not 1<=self.version<=999:
            raise ToolError('invalid versioned tool name')
        if len({a.name for a in self.arguments})!=len(self.arguments):
            raise ToolError('duplicate tool argument')
        if self.risk not in ('read','write','external','privileged') or not _SCOPE.fullmatch(self.scope):
            raise ToolError('invalid risk or execution scope')
        if type(self.max_output_bytes) is not int or not 1<=self.max_output_bytes<=1_048_576:
            raise ToolError('invalid bounded output')
        if type(self.timeout_ms) is not int or not 1<=self.timeout_ms<=60_000:
            raise ToolError('invalid tool deadline')

    @property
    def digest(self)->str:
        from dataclasses import asdict
        b=json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()
        return hashlib.sha256(b).hexdigest()

@dataclass(frozen=True,slots=True)
class ToolInvocation:
    tenant:str
    user:str
    session:str
    invocation_id:str
    tool_name:str
    expected_spec_sha:str
    arguments:dict[str,Any]
    def __post_init__(self):
        for key in ('tenant','user','session','invocation_id'):
            if not _SCOPE.fullmatch(getattr(self,key)):
                raise ToolError('invalid identity or request scope')
        if not _ID.fullmatch(self.tool_name):raise ToolError('invalid tool name')
        if not re.fullmatch(r'[0-9a-f]{64}',self.expected_spec_sha):
            raise ToolError('tool schema digest must be pinned')
        if not isinstance(self.arguments,dict):raise ToolError('tool arguments must be object')
