"""Expiring worker leases for Dragon analysis layers."""
from __future__ import annotations
from dataclasses import dataclass
import math,sqlite3,secrets

@dataclass(frozen=True)
class WorkerLease:
 owner:str;run_id:str;layer:str;worker_id:str;implementation:str;version:str
 token:str;leased_at:float;expires_at:float;generation:int

class DragonWorkerLeases:
 def __init__(self,db:sqlite3.Connection):
  self.db=db
  db.execute("""CREATE TABLE IF NOT EXISTS dragon_worker_leases(
   owner TEXT NOT NULL,run_id TEXT NOT NULL,layer TEXT NOT NULL,worker_id TEXT NOT NULL,
   implementation TEXT NOT NULL,version TEXT NOT NULL,token TEXT NOT NULL,
   leased_at REAL NOT NULL,expires_at REAL NOT NULL,generation INTEGER NOT NULL,
   PRIMARY KEY(owner,run_id,layer))""");db.commit()
 def acquire(self,owner:str,run_id:str,layer:str,worker_id:str,implementation:str,version:str,*,
             now:float,ttl:float,authorized:bool)->WorkerLease:
  if not authorized: raise PermissionError("worker lease requires authorization")
  if not all((owner,run_id,layer,worker_id,implementation,version)) or not math.isfinite(now) or not math.isfinite(ttl) or not 1<=ttl<=3600:
   raise ValueError("invalid worker lease")
  token=secrets.token_hex(32)
  with self.db:
   cur=self.db.execute("""INSERT INTO dragon_worker_leases(
    owner,run_id,layer,worker_id,implementation,version,token,leased_at,expires_at,generation)
    VALUES(?,?,?,?,?,?,?,?,?,1)
    ON CONFLICT(owner,run_id,layer) DO UPDATE SET
      worker_id=excluded.worker_id,implementation=excluded.implementation,
      version=excluded.version,token=excluded.token,leased_at=excluded.leased_at,
      expires_at=excluded.expires_at,generation=dragon_worker_leases.generation+1
    WHERE excluded.leased_at>=dragon_worker_leases.expires_at""",
    (owner,run_id,layer,worker_id,implementation,version,token,now,now+ttl))
   if cur.rowcount!=1:
    raise RuntimeError("analysis layer already leased")
   row=self.db.execute("""SELECT worker_id,implementation,version,token,leased_at,expires_at,generation
    FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=?""",(owner,run_id,layer)).fetchone()
  return WorkerLease(owner,run_id,layer,*row)
 def require(self,lease:WorkerLease,*,now:float,authorized:bool)->WorkerLease:
  if not authorized: raise PermissionError("worker lease validation requires authorization")
  row=self.db.execute("""SELECT worker_id,implementation,version,token,leased_at,expires_at,generation
   FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=?""",(lease.owner,lease.run_id,lease.layer)).fetchone()
  if not row: raise PermissionError("worker lease missing")
  current=WorkerLease(lease.owner,lease.run_id,lease.layer,*row)
  if current!=lease: raise PermissionError("stale or replaced worker lease")
  if not math.isfinite(now) or now>=lease.expires_at: raise PermissionError("worker lease expired")
  return current
 def renew(self,lease:WorkerLease,*,now:float,ttl:float,authorized:bool)->WorkerLease:
  if not authorized: raise PermissionError("worker lease renewal requires authorization")
  if not math.isfinite(now) or not math.isfinite(ttl) or not 1<=ttl<=3600:
   raise ValueError("invalid worker lease renewal")
  current=self.require(lease,now=now,authorized=True)
  if now<current.leased_at: raise ValueError("worker lease renewal time regression")
  renewed=WorkerLease(current.owner,current.run_id,current.layer,current.worker_id,
   current.implementation,current.version,current.token,current.leased_at,now+ttl,current.generation)
  with self.db:
   n=self.db.execute("""UPDATE dragon_worker_leases SET expires_at=?
    WHERE owner=? AND run_id=? AND layer=? AND token=? AND generation=?""",
    (renewed.expires_at,current.owner,current.run_id,current.layer,current.token,current.generation)).rowcount
   if n!=1: raise RuntimeError("worker lease renewal conflict")
  return renewed
 def _release_uncommitted(self,lease:WorkerLease,*,now:float,authorized:bool)->None:
  self.require(lease,now=now,authorized=authorized)
  n=self.db.execute("""DELETE FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=? AND token=?""",
   (lease.owner,lease.run_id,lease.layer,lease.token)).rowcount
  if n!=1: raise RuntimeError("worker lease release conflict")
 def release(self,lease:WorkerLease,*,now:float,authorized:bool)->None:
  with self.db:
   self._release_uncommitted(lease,now=now,authorized=authorized)

