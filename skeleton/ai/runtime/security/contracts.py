"""Typed security identities and secret references for VOL-026."""
from dataclasses import dataclass
class SecurityContractError(ValueError): pass
def _text(value,field,maximum=512):
 if not isinstance(value,str) or not value or value!=value.strip() or len(value)>maximum:
  raise SecurityContractError(f"invalid {field}")
 return value
@dataclass(frozen=True,slots=True)
class SecretRef:
 provider:str
 key:str
 def __post_init__(self):
  _text(self.provider,"provider",128)
  _text(self.key,"key")
@dataclass(frozen=True,slots=True)
class SecurityIdentity:
 principal_id:str
 context_id:str
 def __post_init__(self):
  _text(self.principal_id,"principal_id",256)
  _text(self.context_id,"context_id",256)
