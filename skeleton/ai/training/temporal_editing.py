"""Temporal knowledge-edit authority preserving history and ripple consistency."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalEdit:
 edit_id:str; subject:str; relation:str; old_fact_digest:str; new_fact_digest:str; effective_year:int
 reason:str; evidence_digest:str
 def __post_init__(self):
  if not isinstance(self.edit_id,str) or not self.edit_id.strip() or not isinstance(self.subject,str) or not self.subject.strip() or not isinstance(self.relation,str) or not self.relation.strip(): raise TemporalSignalError("invalid temporal edit identity")
  if isinstance(self.effective_year,bool) or not isinstance(self.effective_year,int) or not 1900<=self.effective_year<=2200: raise TemporalSignalError("invalid temporal edit year")
  if self.reason not in {"correction","world-change"}: raise TemporalSignalError("invalid temporal edit reason")
  for n in ("old_fact_digest","new_fact_digest","evidence_digest"): _hex(getattr(self,n),n)
  if self.old_fact_digest==self.new_fact_digest: raise TemporalSignalError("temporal edit must change fact")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class RippleConstraint:
 constraint_id:str; edit_digest:str; related_fact_digest:str; expected_relation:str; required:bool=True
 def __post_init__(self):
  _hex(self.edit_digest,"edit"); _hex(self.related_fact_digest,"related fact")
  if not isinstance(self.constraint_id,str) or not self.constraint_id.strip() or not isinstance(self.expected_relation,str) or not self.expected_relation.strip() or not isinstance(self.required,bool): raise TemporalSignalError("invalid edit ripple identity")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalEditReceipt:
 edit_digest:str; historical_fact_digest:str; current_fact_digest:str; ripple_digests:tuple[str,...]
 history_preserved:bool; ripple_complete:bool
 @property
 def digest(self): return _digest(self.__dict__)

def validate_temporal_edit(edit,*,historical_fact_digest,current_fact_digest,ripple_constraints=(),satisfied_ripple_digests=()):
 _hex(historical_fact_digest,"historical fact"); _hex(current_fact_digest,"current fact")
 if historical_fact_digest!=edit.old_fact_digest: raise TemporalSignalError("edit historical lineage mismatch")
 if current_fact_digest!=edit.new_fact_digest: raise TemporalSignalError("edit current lineage mismatch")
 constraints=tuple(ripple_constraints)
 if any(not isinstance(c,RippleConstraint) for c in constraints): raise TemporalSignalError("RippleConstraint required")
 if len({c.constraint_id for c in constraints})!=len(constraints): raise TemporalSignalError("duplicate edit ripple constraint")
 satisfied=tuple(satisfied_ripple_digests)
 for d in satisfied: _hex(d,"satisfied ripple")
 if len(set(satisfied))!=len(satisfied): raise TemporalSignalError("duplicate satisfied ripple")
 satisfied=set(satisfied)
 if any(c.edit_digest!=edit.digest for c in constraints): raise TemporalSignalError("ripple constraint edit mismatch")
 required={c.digest for c in constraints if c.required}
 if not required.issubset(satisfied): raise TemporalSignalError("required edit ripple incomplete")
 return TemporalEditReceipt(edit.digest,historical_fact_digest,current_fact_digest,tuple(sorted(required)),True,True)

__all__=["TemporalEdit","RippleConstraint","TemporalEditReceipt","validate_temporal_edit"]
