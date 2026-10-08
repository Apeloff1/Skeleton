"""Append-only custody chain for temporal authority artifacts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalCustodyEntry:
 sequence:int; artifact_digest:str; artifact_kind:str; authority_id:str; previous_digest:str
 def __post_init__(self):
  if not isinstance(self.sequence,int) or self.sequence<0: raise TemporalSignalError("invalid custody sequence")
  _hex(self.artifact_digest,"artifact"); _hex(self.previous_digest,"previous")
  if not self.authority_id or not self.artifact_kind: raise TemporalSignalError("custody identity required")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalCustodyChain:
 entry_digests:tuple[str,...]; head_digest:str; length:int
 @property
 def digest(self): return _digest(self.__dict__)

GENESIS="0"*64
def build_custody_chain(entries):
 entries=tuple(entries); prev=GENESIS
 for i,e in enumerate(entries):
  if e.sequence!=i: raise TemporalSignalError("custody sequence gap")
  if e.previous_digest!=prev: raise TemporalSignalError("custody predecessor mismatch")
  prev=e.digest
 return TemporalCustodyChain(tuple(e.digest for e in entries),prev,len(entries))

def append_custody(entries,*,artifact_digest,artifact_kind,authority_id):
 entries=tuple(entries); chain=build_custody_chain(entries)
 return entries+(TemporalCustodyEntry(len(entries),artifact_digest,artifact_kind,authority_id,chain.head_digest),)

__all__=["TemporalCustodyEntry","TemporalCustodyChain","GENESIS","build_custody_chain","append_custody"]
