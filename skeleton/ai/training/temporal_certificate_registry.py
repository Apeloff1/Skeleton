"""Replay, expiry, and supersession registry for temporal decision certificates."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class CertificateRegistration:
 certificate_digest:str; subject:str; issued_year:int; valid_through_year:int; sequence:int; supersedes_digest:str|None=None
 def __post_init__(self):
  _hex(self.certificate_digest,"certificate")
  if self.supersedes_digest is not None:_hex(self.supersedes_digest,"supersedes")
  if self.valid_through_year<self.issued_year: raise TemporalSignalError("certificate expires before issuance")
  if self.sequence<0: raise TemporalSignalError("invalid certificate sequence")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class CertificateRegistry:
 registrations:tuple[CertificateRegistration,...]=()
 def register(self,item):
  if any(x.certificate_digest==item.certificate_digest for x in self.registrations): raise TemporalSignalError("certificate replay")
  if item.sequence!=len(self.registrations): raise TemporalSignalError("certificate sequence mismatch")
  if item.supersedes_digest is not None and not any(x.certificate_digest==item.supersedes_digest for x in self.registrations): raise TemporalSignalError("unknown superseded certificate")
  return CertificateRegistry(self.registrations+(item,))
 def require_active(self,digest,*,policy_year):
  matches=[x for x in self.registrations if x.certificate_digest==digest]
  if len(matches)!=1: raise TemporalSignalError("certificate not uniquely registered")
  item=matches[0]
  if policy_year>item.valid_through_year: raise TemporalSignalError("temporal certificate expired")
  if any(x.supersedes_digest==digest for x in self.registrations): raise TemporalSignalError("temporal certificate superseded")
  return item.digest
 @property
 def digest(self): return _digest(tuple(x.digest for x in self.registrations))

__all__=["CertificateRegistration","CertificateRegistry"]
