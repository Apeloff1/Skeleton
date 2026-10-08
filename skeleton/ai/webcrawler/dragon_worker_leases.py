"""Expiring worker leases for Dragon analysis layers."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math,sqlite3

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
  with self.db:
   row=self.db.execute("""SELECT worker_id,implementation,version,token,leased_at,expires_at,generation
    FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=?""",(owner,run_id,layer)).fetchone()
   if row and now<row[5]: raise RuntimeError("analysis layer already leased")
   generation=1 if row is None else row[6]+1
   token=sha256(json.dumps([owner,run_id,layer,worker_id,implementation,version,now,ttl,generation],
    separators=(",",":"),allow_nan=False).encode()).hexdigest()
   self.db.execute("""INSERT INTO dragon_worker_leases VALUES(?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(owner,run_id,layer) DO UPDATE SET worker_id=excluded.worker_id,
    implementation=excluded.implementation,version=excluded.version,token=excluded.token,
    leased_at=excluded.leased_at,expires_at=excluded.expires_at,generation=excluded.generation""",
    (owner,run_id,layer,worker_id,implementation,version,token,now,now+ttl,generation))
  return WorkerLease(owner,run_id,layer,worker_id,implementation,version,token,now,now+ttl,generation)
 def require(self,lease:WorkerLease,*,now:float,authorized:bool)->WorkerLease:
  if not authorized: raise PermissionError("worker lease validation requires authorization")
  row=self.db.execute("""SELECT worker_id,implementation,version,token,leased_at,expires_at,generation
   FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=?""",(lease.owner,lease.run_id,lease.layer)).fetchone()
  if not row: raise PermissionError("worker lease missing")
  current=WorkerLease(lease.owner,lease.run_id,lease.layer,*row)
  if current!=lease: raise PermissionError("stale or replaced worker lease")
  if not math.isfinite(now) or now>=lease.expires_at: raise PermissionError("worker lease expired")
  return current
 def release(self,lease:WorkerLease,*,now:float,authorized:bool)->None:
  self.require(lease,now=now,authorized=authorized)
  with self.db:
   n=self.db.execute("""DELETE FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=? AND token=?""",
    (lease.owner,lease.run_id,lease.layer,lease.token)).rowcount
  if n!=1: raise RuntimeError("worker lease release conflict")
