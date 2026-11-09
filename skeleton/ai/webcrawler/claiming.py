"""Fenced work claiming for multi-worker crawler frontiers."""
from __future__ import annotations
from dataclasses import dataclass
from .leases import Lease,SqliteLeaseStore
@dataclass(frozen=True)
class ClaimedWork:
 url:str;lease:Lease
class FrontierClaimer:
 def __init__(self,leases:SqliteLeaseStore,owner:str,ttl:float=60.0):
  if not owner:raise ValueError("owner is required")
  if ttl<=0:raise ValueError("ttl must be positive")
  self.leases=leases;self.owner=owner;self.ttl=ttl
 def claim(self,url:str,*,now:float):
  lease=self.leases.acquire("url:"+url,self.owner,now=now,ttl=self.ttl)
  return ClaimedWork(url,lease) if lease else None
 def renew(self,work:ClaimedWork,*,now:float):
  lease=self.leases.renew(work.lease,now=now,ttl=self.ttl)
  return ClaimedWork(work.url,lease) if lease else None
 def complete(self,work:ClaimedWork)->bool:
  return self.leases.release(work.lease)
