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
  self.index=index;self.ledger=ledger;self.chunker=chunker;self._receipts={}
 def _key(self,doc,decision):return f"{doc.content_hash}:{decision.decision_id}"
 def ingest(self,doc:CrawlDocument,decision:PromotionDecision)->RetrievalBridgeReceipt:
  if decision.action!="promote" or decision.content_hash!=doc.content_hash:
   raise ValueError("retrieval admission requires matching promotion")
  key=self._key(doc,decision)
  if key in self._receipts:return self._receipts[key]
  chunks=tuple(self.chunker.chunk(doc.content_hash,doc.text))
  if len({x.chunk_id for x in chunks})!=len(chunks):raise ValueError("duplicate chunk ids")
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
  receipt=RetrievalBridgeReceipt(doc.content_hash,len(chunks),self.index.revision,tuple(ids))
  self._receipts[key]=receipt
  return receipt
