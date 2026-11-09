"""SQLite-backed multi-worker leases for exclusive frontier ownership."""
from __future__ import annotations
import sqlite3,time,uuid
from dataclasses import dataclass
@dataclass(frozen=True)
class Lease:
 key:str;owner:str;token:str;expires_at:float
class SqliteLeaseStore:
 def __init__(self,path):
  self.db=sqlite3.connect(str(path),isolation_level=None)
  self.db.execute("PRAGMA journal_mode=WAL")
  self.db.execute("""CREATE TABLE IF NOT EXISTS crawl_leases(
    key TEXT PRIMARY KEY,owner TEXT NOT NULL,token TEXT NOT NULL,expires_at REAL NOT NULL)""")
 def acquire(self,key,owner,*,now,ttl):
  if ttl<=0:raise ValueError("ttl must be positive")
  token=uuid.uuid4().hex
  self.db.execute("BEGIN IMMEDIATE")
  try:
   row=self.db.execute("SELECT owner,token,expires_at FROM crawl_leases WHERE key=?",(key,)).fetchone()
   if row and row[2]>now:self.db.execute("ROLLBACK");return None
   self.db.execute("""INSERT INTO crawl_leases VALUES(?,?,?,?) ON CONFLICT(key)
    DO UPDATE SET owner=excluded.owner,token=excluded.token,expires_at=excluded.expires_at""",(key,owner,token,now+ttl))
   self.db.execute("COMMIT");return Lease(key,owner,token,now+ttl)
  except Exception:self.db.execute("ROLLBACK");raise
 def renew(self,lease,*,now,ttl):
  cur=self.db.execute("""UPDATE crawl_leases SET expires_at=? WHERE key=? AND owner=? AND token=? AND expires_at>?""",
   (now+ttl,lease.key,lease.owner,lease.token,now))
  return Lease(lease.key,lease.owner,lease.token,now+ttl) if cur.rowcount==1 else None
 def release(self,lease):
  return self.db.execute("DELETE FROM crawl_leases WHERE key=? AND owner=? AND token=?",
   (lease.key,lease.owner,lease.token)).rowcount==1
