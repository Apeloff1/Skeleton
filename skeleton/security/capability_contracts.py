"""Typed capability-security contracts."""
from dataclasses import dataclass
class SecurityContractError(ValueError): pass
def _text(value,name,limit=512):
 if not isinstance(value,str) or not value or value!=value.strip() or len(value)>limit: raise SecurityContractError("invalid "+name)
 return value
@dataclass(frozen=True,slots=True)
class SecretRef:
 provider:str
 key:str
 def __post_init__(self):
  object.__setattr__(self,"provider",_text(self.provider,"provider"))
  object.__setattr__(self,"key",_text(self.key,"key"))
@dataclass(frozen=True,slots=True)
class CapabilityGrant:
 principal_id:str
 capability:str
 resource:str
 operation:str
 def __post_init__(self):
  for name in ("principal_id","capability","resource","operation"):
   object.__setattr__(self,name,_text(getattr(self,name),name))
