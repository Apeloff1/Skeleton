"""Atomic file persistence for canonical provenance snapshots."""
from __future__ import annotations
import json,os,tempfile
from pathlib import Path
from .provenance import ProvenanceLedger
class ProvenanceCheckpoint:
 def __init__(self,path):self.path=Path(path)
 def save(self,ledger:ProvenanceLedger):
  self.path.parent.mkdir(parents=True,exist_ok=True)
  raw=json.dumps(ledger.snapshot(),sort_keys=True,separators=(",",":"))
  fd,tmp=tempfile.mkstemp(prefix=self.path.name+".",dir=str(self.path.parent))
  try:
   with os.fdopen(fd,"w",encoding="utf-8") as f:
    f.write(raw);f.flush();os.fsync(f.fileno())
   os.replace(tmp,self.path)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 def load(self,bus=None,*,durable=False):
  persist=self.save if durable else None
  if not self.path.exists():return ProvenanceLedger(bus,persist=persist)
  with self.path.open("r",encoding="utf-8") as f:payload=json.load(f)
  return ProvenanceLedger.from_snapshot(payload,bus,persist=persist)
