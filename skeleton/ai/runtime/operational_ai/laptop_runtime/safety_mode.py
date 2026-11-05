"""Safety controls for local inference: no hosted fallback or model-directed tools."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import refuse

@dataclass(frozen=True,slots=True)
class SafetyMode:
    allow_network:bool=False
    model_tool_authority:bool=False
    allow_implicit_memory:bool=False
    allow_remote_provider:bool=False
    require_source_receipt:bool=True
    require_isolation:bool=True

    def __post_init__(self):
        for key in self.__dataclass_fields__:
            if type(getattr(self,key)) is not bool:
                refuse("explicit AI safety toggle required")
        if (self.allow_network or self.model_tool_authority or
            self.allow_implicit_memory or self.allow_remote_provider or
            not self.require_source_receipt or not self.require_isolation):
            refuse("first-usable laptop safety mode cannot be weakened")

    def to_record(self):
        return {k:getattr(self,k) for k in self.__dataclass_fields__}
