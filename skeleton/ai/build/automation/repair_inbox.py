"""Durable, deduplicated inbox for CI-derived autonomous repair tasks."""
from __future__ import annotations
import hashlib,json,os,tempfile
from dataclasses import dataclass,asdict
from pathlib import Path
from .ci_repair_queue import CIRepairTask
@dataclass
class RepairInbox:
 head_sha:str;tasks:dict[str,dict];revision:int=0;sha256:str=""
 @classmethod
 def empty(cls,head_sha:str):return cls(head_sha,{})
 def add(self,items:tuple[CIRepairTask,...]):
  for x in items:self.tasks.setdefault(x.id,asdict(x))
  self.revision+=1;return self
 def seal(self):
  body={"head_sha":self.head_sha,"tasks":self.tasks,"revision":self.revision}
  self.sha256=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest();return self
 def write(self,path:Path):
  self.seal();path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix="."+path.name+".")
  try:
   with os.fdopen(fd,"w") as h:json.dump(asdict(self),h,sort_keys=True,indent=2);h.write("\n");h.flush();os.fsync(h.fileno())
   os.replace(tmp,path)
  except BaseException:Path(tmp).unlink(missing_ok=True);raise
