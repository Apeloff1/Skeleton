"""Durable fenced idempotency keys for crawler downstream ingestion."""
from __future__ import annotations
import json,sqlite3,uuid
from dataclasses import dataclass
@dataclass(frozen=True)
class IngestionLease:
 key:str;owner:str;token:str;expires_at:float
class DurableIngestionRegistry:
 def __init__(self,db:sqlite3.Connection):self.db=db
 def reserve(self,key,owner,*,now,ttl):
  if not key or not owner or ttl<=0:raise ValueError("key, owner and positive ttl required")
  token=uuid.uuid4().hex
  self.db.execute("BEGIN IMMEDIATE")
  try:
   row=self.db.execute("SELECT state,owner,token,lease_expires,receipt FROM ingestion_receipts WHERE ingestion_key=?",(key,)).fetchone()
   if row and row[0]=="complete":
    self.db.execute("COMMIT");return json.loads(row[4])
   if row and row[3] is not None and row[3]>now:
    self.db.execute("COMMIT");return None
   self.db.execute("""INSERT INTO ingestion_receipts VALUES(?,?,?,?,?,NULL)
    ON CONFLICT(ingestion_key) DO UPDATE SET state='reserved',owner=excluded.owner,token=excluded.token,lease_expires=excluded.lease_expires,receipt=NULL""",
    (key,"reserved",owner,token,now+ttl))
   self.db.execute("COMMIT");return IngestionLease(key,owner,token,now+ttl)
  except Exception:self.db.execute("ROLLBACK");raise
 def complete(self,lease:IngestionLease,receipt):
  raw=json.dumps(receipt,sort_keys=True,separators=(",",":"))
  with self.db:
   cur=self.db.execute("""UPDATE ingestion_receipts SET state='complete',receipt=?,lease_expires=NULL
    WHERE ingestion_key=? AND state='reserved' AND owner=? AND token=?""",(raw,lease.key,lease.owner,lease.token))
  return cur.rowcount==1
 def abandon(self,lease:IngestionLease):
  with self.db:
   cur=self.db.execute("DELETE FROM ingestion_receipts WHERE ingestion_key=? AND state='reserved' AND owner=? AND token=?",
    (lease.key,lease.owner,lease.token))
  return cur.rowcount==1
 def receipt(self,key):
  row=self.db.execute("SELECT receipt FROM ingestion_receipts WHERE ingestion_key=? AND state='complete'",(key,)).fetchone()
  return json.loads(row[0]) if row else None
