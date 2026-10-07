"""Canonical crawler handoff into Skeleton retrieval index and provenance ledger."""
from __future__ import annotations
from dataclasses import dataclass
from .core import CrawlDocument
from .governance import PromotionDecision

@dataclass(frozen=True)
class RetrievalBridgeReceipt:
 content_hash:str;chunks:int;index_revision:int;provenance_entry_ids:tuple[str,...]

class CanonicalRetrievalBridge:
 def __init__(self,index,ledger,chunker):
  self.index=index;self.ledger=ledger;self.chunker=chunker
 def ingest(self,doc:CrawlDocument,decision:PromotionDecision)->RetrievalBridgeReceipt:
  if decision.action!="promote" or decision.content_hash!=doc.content_hash:
   raise ValueError("retrieval admission requires matching promotion")
  chunks=self.chunker.chunk(doc.content_hash,doc.text)
  ids=[]
  for chunk in chunks:
   self.index.add(chunk.chunk_id,chunk.text)
   entry=self.ledger.record(
    source=doc.canonical_url,operation="crawler.promoted_chunk",
    input_data=doc.content_hash,output_data=chunk.text,
    metadata={"content_hash":doc.content_hash,"chunk_id":chunk.chunk_id,
              "start":chunk.start,"end":chunk.end,
              "promotion_decision_id":decision.decision_id})
   ids.append(entry.entry_id)
  return RetrievalBridgeReceipt(doc.content_hash,len(chunks),self.index.revision,tuple(ids))
