"""Replay-resistant registry for temporal authority receipts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class TemporalAuthorityEntry:
 sequence:int; authority_digest:str; subject:str; policy_year:int; previous_entry_digest:str|None
 def __post_init__(self):
  if isinstance(self.sequence,bool) or not isinstance(self.sequence,int) or self.sequence<1: raise TemporalSignalError("invalid temporal sequence")
  if not isinstance(self.subject,str) or not self.subject.strip(): raise TemporalSignalError("invalid temporal subject")
  if isinstance(self.policy_year,bool) or not isinstance(self.policy_year,int) or not 1900<=self.policy_year<=2200: raise TemporalSignalError("invalid temporal policy year")
  for d in (self.authority_digest,self.previous_entry_digest):
   if d is not None and (not isinstance(d,str) or len(d)!=64 or any(c not in "0123456789abcdef" for c in d)): raise TemporalSignalError("invalid temporal authority digest")
 @property
 def digest(self): return _digest(self.__dict__)

class TemporalAuthorityLedger:
 def __init__(self,entries=()):
  self._entries=list(entries); self._validate()
 def _validate(self):
  prev=None
  for i,e in enumerate(self._entries,1):
   if e.sequence!=i: raise TemporalSignalError("temporal authority sequence gap")
   if e.previous_entry_digest!=prev: raise TemporalSignalError("temporal authority chain mismatch")
   prev=e.digest
  if len({e.authority_digest for e in self._entries})!=len(self._entries): raise TemporalSignalError("replayed temporal authority")
 def append(self,authority_digest,subject,policy_year):
  if authority_digest in {e.authority_digest for e in self._entries}: raise TemporalSignalError("replayed temporal authority")
  prev=self._entries[-1].digest if self._entries else None
  e=TemporalAuthorityEntry(len(self._entries)+1,authority_digest,subject,policy_year,prev); self._entries.append(e); return e
 def snapshot(self):
  body={"schema":"temporal-authority-ledger.v1","entries":[dict(e.__dict__) for e in self._entries]}
  return {**body,"digest":_digest(body)}
 @classmethod
 def restore(cls,snapshot):
  body={k:snapshot[k] for k in ("schema","entries")}
  if snapshot.get("schema")!="temporal-authority-ledger.v1" or snapshot.get("digest")!=_digest(body): raise TemporalSignalError("invalid temporal ledger snapshot")
  return cls(TemporalAuthorityEntry(**e) for e in snapshot["entries"])

__all__=["TemporalAuthorityEntry","TemporalAuthorityLedger"]
