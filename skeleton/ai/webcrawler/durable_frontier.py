"""Atomic SQLite frontier for distributed crawler workers."""
from __future__ import annotations
import sqlite3,uuid
from dataclasses import dataclass
@dataclass(frozen=True)
class DurableClaim:
 url:str;ready_at:float;priority:float;depth:int;parent_url:str|None;attempts:int
 owner:str;token:str;expires_at:float
class DurableFrontier:
 def __init__(self,db:sqlite3.Connection):self.db=db
 def enqueue(self,url,*,ready_at=0.0,priority=0.0,depth=0,parent_url=None,attempts=0):
  with self.db:
   cur=self.db.execute("""INSERT OR IGNORE INTO durable_frontier
    (url,ready_at,priority,depth,parent_url,attempts) VALUES(?,?,?,?,?,?)""",
    (url,ready_at,priority,depth,parent_url,attempts))
  return cur.rowcount==1
 def claim(self,owner,*,now,ttl):
  if not owner or ttl<=0:raise ValueError("owner and positive ttl required")
  token=uuid.uuid4().hex
  self.db.execute("BEGIN IMMEDIATE")
  try:
   row=self.db.execute("""SELECT url,ready_at,priority,depth,parent_url,attempts
    FROM durable_frontier WHERE ready_at<=? AND (owner IS NULL OR lease_expires<=?)
    ORDER BY priority,ready_at,url LIMIT 1""",(now,now)).fetchone()
   if not row:self.db.execute("COMMIT");return None
   cur=self.db.execute("""UPDATE durable_frontier SET owner=?,lease_token=?,lease_expires=?
    WHERE url=? AND (owner IS NULL OR lease_expires<=?)""",(owner,token,now+ttl,row[0],now))
   if cur.rowcount!=1:self.db.execute("ROLLBACK");return None
   self.db.execute("COMMIT");return DurableClaim(*row,owner,token,now+ttl)
  except Exception:self.db.execute("ROLLBACK");raise
 def complete(self,claim):
  with self.db:
   cur=self.db.execute("DELETE FROM durable_frontier WHERE url=? AND owner=? AND lease_token=?",
    (claim.url,claim.owner,claim.token))
  return cur.rowcount==1
 def retry(self,claim,*,ready_at,attempts):
  with self.db:
   cur=self.db.execute("""UPDATE durable_frontier SET ready_at=?,attempts=?,owner=NULL,lease_token=NULL,lease_expires=NULL
    WHERE url=? AND owner=? AND lease_token=?""",(ready_at,attempts,claim.url,claim.owner,claim.token))
  return cur.rowcount==1
 def renew(self,claim,*,now,ttl):
  if ttl<=0:raise ValueError("ttl must be positive")
  with self.db:
   cur=self.db.execute("""UPDATE durable_frontier SET lease_expires=?
    WHERE url=? AND owner=? AND lease_token=? AND lease_expires>?""",(now+ttl,claim.url,claim.owner,claim.token,now))
  return DurableClaim(claim.url,claim.ready_at,claim.priority,claim.depth,claim.parent_url,claim.attempts,claim.owner,claim.token,now+ttl) if cur.rowcount==1 else None
 def size(self):return self.db.execute("SELECT COUNT(*) FROM durable_frontier").fetchone()[0]
