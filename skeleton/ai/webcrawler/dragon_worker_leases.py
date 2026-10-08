"""Expiring worker leases for Dragon analysis layers."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
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
   PRIMARY KEY(owner,run_id,layer))""")
  db.execute("""CREATE TABLE IF NOT EXISTS dragon_worker_lease_history(
   owner TEXT NOT NULL,run_id TEXT NOT NULL,layer TEXT NOT NULL,generation INTEGER NOT NULL,
   worker_id TEXT NOT NULL,implementation TEXT NOT NULL,version TEXT NOT NULL,
   token_digest TEXT NOT NULL,leased_at REAL NOT NULL,expires_at REAL NOT NULL,
   released_at REAL NOT NULL,
   PRIMARY KEY(owner,run_id,layer,generation),
   UNIQUE(owner,run_id,layer,token_digest))""");db.commit()
 def acquire(self,owner:str,run_id:str,layer:str,worker_id:str,implementation:str,version:str,*,
             now:float,ttl:float,authorized:bool)->WorkerLease:
  if not authorized: raise PermissionError("worker lease requires authorization")
  if not all((owner,run_id,layer,worker_id,implementation,version)) or not math.isfinite(now) or not math.isfinite(ttl) or not 1<=ttl<=3600:
   raise ValueError("invalid worker lease")
  token=secrets.token_hex(32)
  # Serialize replacement so an expired generation is archived before it is overwritten.
  if self.db.in_transaction: raise RuntimeError("worker lease acquisition requires transaction boundary")
  self.db.execute("BEGIN IMMEDIATE")
  try:
   old=self.db.execute("""SELECT worker_id,implementation,version,token,leased_at,expires_at,generation
    FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=?""",(owner,run_id,layer)).fetchone()
   if old and now<old[5]: raise RuntimeError("analysis layer already leased")
   generation=1 if not old else old[6]+1
   if old:
    digest=sha256(old[3].encode()).hexdigest()
    self.db.execute("""INSERT INTO dragon_worker_lease_history VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
     (owner,run_id,layer,old[6],old[0],old[1],old[2],digest,old[4],old[5],now))
    self.db.execute("DELETE FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=?",
     (owner,run_id,layer))
   self.db.execute("""INSERT INTO dragon_worker_leases VALUES(?,?,?,?,?,?,?,?,?,?)""",
    (owner,run_id,layer,worker_id,implementation,version,token,now,now+ttl,generation))
   self.db.commit()
  except Exception:
   self.db.rollback();raise
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
  token_digest=sha256(lease.token.encode()).hexdigest()
  existing=self.db.execute("""SELECT worker_id,implementation,version,token_digest,
   leased_at,expires_at,released_at FROM dragon_worker_lease_history
   WHERE owner=? AND run_id=? AND layer=? AND generation=?""",
   (lease.owner,lease.run_id,lease.layer,lease.generation)).fetchone()
  expected=(lease.worker_id,lease.implementation,lease.version,token_digest,
   lease.leased_at,lease.expires_at,now)
  if existing and existing!=expected: raise ValueError("immutable worker lease history conflict")
  if not existing:
   self.db.execute("""INSERT INTO dragon_worker_lease_history VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
    (lease.owner,lease.run_id,lease.layer,lease.generation,lease.worker_id,
     lease.implementation,lease.version,token_digest,lease.leased_at,lease.expires_at,now))
  n=self.db.execute("""DELETE FROM dragon_worker_leases WHERE owner=? AND run_id=? AND layer=? AND token=?""",
   (lease.owner,lease.run_id,lease.layer,lease.token)).rowcount
  if n!=1: raise RuntimeError("worker lease release conflict")
 def history(self,owner:str,run_id:str,layer:str,generation:int,*,authorized:bool):
  if not authorized: raise PermissionError("worker lease history read requires authorization")
  row=self.db.execute("""SELECT worker_id,implementation,version,token_digest,
   leased_at,expires_at,released_at FROM dragon_worker_lease_history
   WHERE owner=? AND run_id=? AND layer=? AND generation=?""",
   (owner,run_id,layer,generation)).fetchone()
  if not row: raise KeyError("worker lease history not found")
  return row
 def release(self,lease:WorkerLease,*,now:float,authorized:bool)->None:
  with self.db:
   self._release_uncommitted(lease,now=now,authorized=authorized)

