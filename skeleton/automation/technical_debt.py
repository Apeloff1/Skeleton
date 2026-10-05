"""Owned technical-debt ledger for VOL-115."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class DebtError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise DebtError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class DebtImpact:
 operational_interest:int;engineering_interest:int;risk:int
 def __post_init__(self):
  for f in ("operational_interest","engineering_interest","risk"):\n   v=getattr(self,f)\n   if not isinstance(v,int) or isinstance(v,bool) or v<0:raise DebtError("debt impact must be nonnegative integers")
@dataclass(frozen=True,slots=True)
class DebtItem:
 debt_id:str;source:str;contract_ids:tuple[str,...];owner_id:str;target_disposition:str;impact:DebtImpact
 def __post_init__(self):
  object.__setattr__(self,"debt_id",_id(self.debt_id,"debt_id"));object.__setattr__(self,"owner_id",_id(self.owner_id,"owner_id"))
  if not isinstance(self.contract_ids,tuple):raise DebtError("contract_ids must be tuple")\n  contracts=tuple(_id(x,"contract_id") for x in self.contract_ids)\n  if len(set(contracts))!=len(contracts):raise DebtError("duplicate affected contract")\n  contracts=tuple(sorted(contracts))
  if not isinstance(self.source,str) or not isinstance(self.target_disposition,str) or not self.source.strip() or not contracts or not self.target_disposition.strip():raise DebtError("source contracts and disposition required")\n  if not isinstance(self.impact,DebtImpact):raise DebtError("impact must be DebtImpact")
  object.__setattr__(self,"contract_ids",contracts)
@dataclass(frozen=True,slots=True)
class DebtRetirement:
 debt_id:str;migration_evidence_id:str;compatibility_evidence_id:str;rollback_evidence_id:str;verification_evidence_id:str
 def __post_init__(self):
  for f in ("debt_id","migration_evidence_id","compatibility_evidence_id","rollback_evidence_id","verification_evidence_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
class DebtLedger:
 def __init__(self,items):\n  if not isinstance(items,tuple) or any(not isinstance(x,DebtItem) for x in items):raise DebtError("items must be typed tuple")\n  if len({x.debt_id for x in items})!=len(items):raise DebtError("duplicate debt identity")\n  self.items={x.debt_id:x for x in items};self.retired={}
 def interest(self,debt_id):\n  debt_id=_id(debt_id,"debt_id")\n  if debt_id not in self.items:raise DebtError("unknown debt")\n  i=self.items[debt_id].impact;return i.operational_interest+i.engineering_interest+i.risk
 def retire(self,receipt):
  if receipt.debt_id not in self.items:raise DebtError("unknown debt")
  if receipt.debt_id in self.retired:raise DebtError("debt already retired")
  self.retired[receipt.debt_id]=receipt;return receipt
 def active_by_risk(self):return tuple(sorted((x for x in self.items.values() if x.debt_id not in self.retired),key=lambda x:(-self.interest(x.debt_id),x.debt_id)))
