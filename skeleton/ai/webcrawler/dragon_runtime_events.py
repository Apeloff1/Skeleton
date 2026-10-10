"""Append-only forensic event ledger for Dragon analysis execution."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math,sqlite3

@dataclass(frozen=True)
class RuntimeEvent:
 owner:str; run_id:str; sequence:int; event_type:str; layer:str
 outcome:str; evidence_fingerprint:str; error_code:str; occurred_at:float
 previous_hash:str; event_hash:str

class DragonRuntimeEventLedger:
 def __init__(self,db:sqlite3.Connection):
  self.db=db
  db.execute("""CREATE TABLE IF NOT EXISTS dragon_runtime_events(
   owner TEXT NOT NULL,run_id TEXT NOT NULL,sequence INTEGER NOT NULL,
   event_type TEXT NOT NULL,layer TEXT NOT NULL,outcome TEXT NOT NULL,
   evidence_fingerprint TEXT NOT NULL,error_code TEXT NOT NULL,
   occurred_at REAL NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL,
   PRIMARY KEY(owner,run_id,sequence),UNIQUE(owner,run_id,event_hash))""");db.commit()
 def _append_uncommitted(self,owner:str,run_id:str,*,event_type:str,layer:str,outcome:str,
            evidence_fingerprint:str="",error_code:str="",occurred_at:float,
            authorized:bool)->RuntimeEvent:
  if not authorized: raise PermissionError("runtime event write requires authorization")
  if not owner or not run_id or not event_type or not layer or not outcome or not math.isfinite(occurred_at):
   raise ValueError("invalid runtime event")
  if evidence_fingerprint and (len(evidence_fingerprint)!=64 or any(c not in "0123456789abcdef" for c in evidence_fingerprint)):
   raise ValueError("invalid event evidence fingerprint")
  if len(error_code)>128: raise ValueError("error code too long")
  if isinstance(occurred_at,bool) or not isinstance(occurred_at,(int,float)) or occurred_at<0:
   raise ValueError("invalid runtime event time")
  occurred_at=float(occurred_at)
  row=self.db.execute("""SELECT sequence,event_hash,occurred_at FROM dragon_runtime_events
   WHERE owner=? AND run_id=? ORDER BY sequence DESC LIMIT 1""",(owner,run_id)).fetchone()
  seq=1 if row is None else row[0]+1;prev="0"*64 if row is None else row[1]
  if row is not None and occurred_at<row[2]: raise ValueError("runtime event time regression")
  body=[owner,run_id,seq,event_type,layer,outcome,evidence_fingerprint,error_code,occurred_at,prev]
  h=sha256(json.dumps(body,separators=(",",":"),allow_nan=False).encode()).hexdigest()
  self.db.execute("INSERT INTO dragon_runtime_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
   (owner,run_id,seq,event_type,layer,outcome,evidence_fingerprint,error_code,occurred_at,prev,h))
  return RuntimeEvent(owner,run_id,seq,event_type,layer,outcome,evidence_fingerprint,error_code,occurred_at,prev,h)

 def append(self,owner:str,run_id:str,*,event_type:str,layer:str,outcome:str,
            evidence_fingerprint:str="",error_code:str="",occurred_at:float,
            authorized:bool)->RuntimeEvent:
  with self.db:
   return self._append_uncommitted(owner,run_id,event_type=event_type,layer=layer,outcome=outcome,
    evidence_fingerprint=evidence_fingerprint,error_code=error_code,occurred_at=occurred_at,
    authorized=authorized)
 def events(self,owner:str,run_id:str,*,authorized:bool)->tuple[RuntimeEvent,...]:
  if not authorized: raise PermissionError("runtime event read requires authorization")
  rows=self.db.execute("""SELECT owner,run_id,sequence,event_type,layer,outcome,evidence_fingerprint,
   error_code,occurred_at,previous_hash,event_hash FROM dragon_runtime_events
   WHERE owner=? AND run_id=? ORDER BY sequence""",(owner,run_id)).fetchall()
  return tuple(RuntimeEvent(*r) for r in rows)
 def verify(self,owner:str,run_id:str,*,authorized:bool)->bool:
  events=self.events(owner,run_id,authorized=authorized);prev="0"*64
  for e in events:
   body=[e.owner,e.run_id,e.sequence,e.event_type,e.layer,e.outcome,e.evidence_fingerprint,e.error_code,e.occurred_at,prev]
   h=sha256(json.dumps(body,separators=(",",":"),allow_nan=False).encode()).hexdigest()
   if e.event_hash!=h and float(e.occurred_at).is_integer():
    body[8]=int(e.occurred_at)
    h=sha256(json.dumps(body,separators=(",",":"),allow_nan=False).encode()).hexdigest()
   if e.previous_hash!=prev or e.event_hash!=h:return False
   prev=e.event_hash
  return True
