"""Truthful visual event protocol for the baby-dragon crawler UI."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json
_ALLOWED={"frontier_discovered","dragon_travel","visual_probe","robots_check","fetch_started","fetch_received","policy_rejected","acquisition_accepted","burn_started","burn_chunk","burn_complete","retry_wait","crawl_complete"}
@dataclass(frozen=True)
class DragonCrawlEvent:
 sequence:int;kind:str;url:str;at:float;payload:dict
 @property
 def event_id(self):
  raw=json.dumps({"sequence":self.sequence,"kind":self.kind,"url":self.url,"at":self.at,"payload":self.payload},sort_keys=True,separators=(",",":"))
  return hashlib.sha256(raw.encode()).hexdigest()
 def to_dict(self):return {"schema":"skeleton.ai.dragon_crawl.event.v1","event_id":self.event_id,**asdict(self)}
class DragonEventStream:
 def __init__(self):self.sequence=0;self.events=[]
 def emit(self,kind,url,*,at,payload=None):
  if kind not in _ALLOWED:raise ValueError("unknown dragon crawl event")
  self.sequence+=1;e=DragonCrawlEvent(self.sequence,kind,url,float(at),dict(payload or {}));self.events.append(e);return e
