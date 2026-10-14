"""Optional instrumentation adapter: crawler remains headless; UI consumes events."""
from __future__ import annotations
class DragonCrawlObserver:
 def __init__(self,stream):self.stream=stream
 def discovered(self,url,*,at,depth,parent=None):return self.stream.emit("frontier_discovered",url,at=at,payload={"depth":depth,"parent":parent})
 def travel(self,url,*,at):return self.stream.emit("dragon_travel",url,at=at)
 def robots(self,url,*,at):return self.stream.emit("robots_check",url,at=at)
 def fetch_started(self,url,*,at):return self.stream.emit("fetch_started",url,at=at)
 def received(self,doc,*,at):return self.stream.emit("fetch_received",doc.canonical_url,at=at,payload={"content_hash":doc.content_hash,"bytes_text":len(doc.text.encode("utf-8")),"links":len(doc.links)})
 def accepted(self,doc,*,at):return self.stream.emit("acquisition_accepted",doc.canonical_url,at=at,payload={"content_hash":doc.content_hash,"source_score":doc.source_score})
 def burn(self,doc,chunks,*,at):
  self.stream.emit("burn_started",doc.canonical_url,at=at,payload={"content_hash":doc.content_hash,"chunks":len(chunks)})
  for i,c in enumerate(chunks):self.stream.emit("burn_chunk",doc.canonical_url,at=at,payload={"ordinal":i,"chunk_id":c.chunk_id})
  return self.stream.emit("burn_complete",doc.canonical_url,at=at,payload={"content_hash":doc.content_hash,"chunks":len(chunks)})
 def rejected(self,url,reason,*,at):return self.stream.emit("policy_rejected",url,at=at,payload={"reason":reason})
