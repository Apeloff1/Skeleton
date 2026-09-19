"""Immutable execution context propagated across shell orchestration."""

from __future__ import annotations

from dataclasses import dataclass,field,replace
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping

_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,159}$")

@dataclass(frozen=True)
class ExecutionContext:
    correlation_id:str
    principal:str="anonymous"
    request_id:str=""
    parent_correlation_id:str=""
    tags:frozenset[str]=frozenset()
    attributes:Mapping[str,str]=field(default_factory=dict)

    def __post_init__(self)->None:
        for name,value,required in (
            ("correlation_id",self.correlation_id,True),
            ("principal",self.principal,True),
            ("request_id",self.request_id,False),
            ("parent_correlation_id",self.parent_correlation_id,False),
        ):
            if required and not value:
                raise ValueError(f"{name} is required")
            if value and (not isinstance(value,str) or not _ID.fullmatch(value)):
                raise ValueError(f"invalid {name}")
        tags=frozenset(self.tags)
        if len(tags)>64 or any(not isinstance(tag,str) or not _ID.fullmatch(tag) for tag in tags):
            raise ValueError("invalid execution context tags")
        attrs=dict(self.attributes)
        if len(attrs)>64:
            raise ValueError("too many execution context attributes")
        if any(
            not isinstance(key,str) or not _ID.fullmatch(key)
            or not isinstance(value,str) or len(value)>512
            for key,value in attrs.items()
        ):
            raise ValueError("invalid execution context attribute")
        object.__setattr__(self,"tags",tags)
        object.__setattr__(self,"attributes",MappingProxyType(attrs))

    def child(self,correlation_id:str,**changes)->"ExecutionContext":
        return replace(
            self,
            correlation_id=correlation_id,
            parent_correlation_id=self.correlation_id,
            **changes,
        )

    def to_dict(self)->dict[str,object]:
        return {
            "correlation_id":self.correlation_id,
            "principal":self.principal,
            "request_id":self.request_id,
            "parent_correlation_id":self.parent_correlation_id,
            "tags":sorted(self.tags),
            "attributes":dict(self.attributes),
        }

    @property
    def fingerprint(self)->str:
        raw=json.dumps(self.to_dict(),sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(raw).hexdigest()
