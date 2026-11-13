"""Explicit tool contracts bind schemas, risk, authority and owners."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Callable
from ..authority.canonical import ContractViolation,canonical_bytes
from ..authority.identity import require_id
from .schemas import validate


@dataclass(frozen=True,slots=True)
class ToolDefinition:
    name:str
    argument_schema:dict
    risk:str
    version:int=1
    description:str=""

    def __post_init__(self):
        require_id(self.name,field="tool name")
        if self.risk not in {"readonly","write","external"}:
            raise ContractViolation("unknown tool risk class")
        if type(self.version) is not int or not 1<=self.version<=2**16:
            raise ContractViolation("invalid tool contract version")
        canonical_bytes(self.argument_schema)
        from .schemas import validate
        if not isinstance(self.argument_schema,dict) or self.argument_schema.get("type")!="object":
            raise ContractViolation("tool request must declare object schema")


class ToolCatalog:
    def __init__(self):
        self._definitions:dict[str,ToolDefinition]={}
        self._implementations:dict[str,Callable[...,dict]]={}

    def register(self,definition:ToolDefinition,executor:Callable[...,dict])->None:
        if definition.name in self._definitions:
            raise ContractViolation("duplicate tool name")
        if not callable(executor):
            raise ContractViolation("tool requires registered executable")
        self._definitions[definition.name]=definition
        self._implementations[definition.name]=executor

    def resolve(self,name:str)->tuple[ToolDefinition,Callable[...,dict]]:
        require_id(name,field="tool name")
        if name not in self._definitions:
            raise ContractViolation("unregistered tool invocation")
        return self._definitions[name],self._implementations[name]

    def describe(self)->tuple[dict,...]:
        return tuple({"name":x.name,"version":x.version,"risk":x.risk,
                      "schema":x.argument_schema,"description":x.description}
                     for x in sorted(self._definitions.values(),key=lambda d:d.name))
