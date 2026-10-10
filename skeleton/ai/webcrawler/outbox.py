"""Durable deterministic operation plan for resumable downstream ingestion."""
from __future__ import annotations
import hashlib,json,sqlite3
from dataclasses import dataclass
@dataclass(frozen=True)
class OutboxOperation:
 operation_id:str;ingestion_key:str;ordinal:int;payload:dict;state:str;result:dict|None
class IngestionOutbox:
 def __init__(self,db:sqlite3.Connection):self.db=db
 @staticmethod
 def operation_id(key,ordinal,payload):
  raw=json.dumps(payload,sort_keys=True,separators=(",",":"))
  return hashlib.sha256(f"{key}:{ordinal}:{raw}".encode()).hexdigest()
 def plan(self,key,payloads):
  rows=[]
  with self.db:
   for ordinal,payload in enumerate(payloads):
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"));oid=self.operation_id(key,ordinal,payload)
    self.db.execute("INSERT OR IGNORE INTO ingestion_outbox(operation_id,ingestion_key,ordinal,payload) VALUES(?,?,?,?)",(oid,key,ordinal,raw))
    row=self.db.execute("SELECT operation_id,payload,state,result FROM ingestion_outbox WHERE ingestion_key=? AND ordinal=?",(key,ordinal)).fetchone()
    if row[0]!=oid or row[1]!=raw:raise ValueError("ingestion plan changed after persistence")
    rows.append(OutboxOperation(row[0],key,ordinal,json.loads(row[1]),row[2],json.loads(row[3]) if row[3] else None))
  return tuple(rows)
 def pending(self,key):
  rows=self.db.execute("SELECT operation_id,ordinal,payload,state,result FROM ingestion_outbox WHERE ingestion_key=? ORDER BY ordinal",(key,)).fetchall()
  return tuple(OutboxOperation(r[0],key,r[1],json.loads(r[2]),r[3],json.loads(r[4]) if r[4] else None) for r in rows)
 def complete(self,operation_id,result):
  raw=json.dumps(result,sort_keys=True,separators=(",",":"))
  with self.db:self.db.execute("UPDATE ingestion_outbox SET state='complete',result=? WHERE operation_id=?",(raw,operation_id))
