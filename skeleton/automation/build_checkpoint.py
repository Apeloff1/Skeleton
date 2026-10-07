"""Durable cross-run checkpoint binding all autonomous build authorities."""
from __future__ import annotations
import hashlib,json,os,tempfile
from dataclasses import dataclass,asdict
from pathlib import Path
@dataclass(frozen=True)
class BuildCheckpoint:
 head_sha:str;generation_id:str;campaign_epoch:int;build_cycle:int;allocation_sha256:str;execution_receipt_sha256:str;ci_evidence_sha256:str=""
 def digest(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(",",":")).encode()).hexdigest()
 def write(self,path:Path):
  payload={"schema":"autonomous-studio.build-checkpoint.v1","checkpoint":asdict(self),"sha256":self.digest()}
  path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix="."+path.name+".")
  try:
   with os.fdopen(fd,"w") as h:json.dump(payload,h,sort_keys=True,indent=2);h.write("\n");h.flush();os.fsync(h.fileno())
   os.replace(tmp,path)
  except BaseException:Path(tmp).unlink(missing_ok=True);raise
