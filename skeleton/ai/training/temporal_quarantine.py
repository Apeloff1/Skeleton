"""Quarantine contradictory or hypothetical temporal evidence before learning."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class QuarantineItem:
 item_id:str; content_digest:str; reason_code:str; admitted_year:int; source_digest:str
 def __post_init__(self):
  if not isinstance(self.item_id,str) or not self.item_id.strip(): raise TemporalSignalError("invalid quarantine item identity")
  if self.reason_code not in _ALLOWED: raise TemporalSignalError("unsupported quarantine reason")
  for name in ("content_digest","source_digest"):
   d=getattr(self,name)
   if not isinstance(d,str) or len(d)!=64 or any(c not in "0123456789abcdef" for c in d): raise TemporalSignalError("invalid quarantine "+name)
  if isinstance(self.admitted_year,bool) or not isinstance(self.admitted_year,int) or not 1900<=self.admitted_year<=2200: raise TemporalSignalError("invalid quarantine year")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class QuarantineResolution:
 item_digest:str; resolution:str; evidence_digest:str; resolver_id:str
 def __post_init__(self):
  for name in ("item_digest","evidence_digest"):
   d=getattr(self,name)
   if not isinstance(d,str) or len(d)!=64 or any(c not in "0123456789abcdef" for c in d): raise TemporalSignalError("invalid resolution "+name)
  if self.resolution not in {"release-retrieval","release-learning","reject"}: raise TemporalSignalError("invalid quarantine resolution")
  if not isinstance(self.resolver_id,str) or not self.resolver_id.strip(): raise TemporalSignalError("resolver identity required")
 @property
 def digest(self): return _digest(self.__dict__)

_ALLOWED={"unresolved-contradiction","counterfactual-content","provenance-conflict","regime-instability","future-leakage"}
def quarantine(content_digest,*,item_id,reason_code,admitted_year,source_digest):
 if reason_code not in _ALLOWED: raise TemporalSignalError("unsupported quarantine reason")
 return QuarantineItem(item_id,content_digest,reason_code,admitted_year,source_digest)

def resolve_quarantine(item,*,resolution,evidence_digest,resolver_id):
 if resolution not in {"release-retrieval","release-learning","reject"}: raise TemporalSignalError("invalid quarantine resolution")
 if not resolver_id: raise TemporalSignalError("resolver identity required")
 return QuarantineResolution(item.digest,resolution,evidence_digest,resolver_id)

def require_learning_release(resolution):
 if resolution.resolution!="release-learning": raise TemporalSignalError("quarantine not released for learning")
 return resolution.digest
__all__=["QuarantineItem","QuarantineResolution","quarantine","resolve_quarantine","require_learning_release"]
