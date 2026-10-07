"""Canonical crawler handoff into Skeleton retrieval index and provenance ledger."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from .core import CrawlDocument
from .governance import PromotionDecision
from .ingestion_registry import DurableIngestionRegistry,IngestionLease
from .outbox import IngestionOutbox
@dataclass(frozen=True)
class RetrievalBridgeReceipt:
 content_hash:str;chunks:int;index_revision:int;provenance_entry_ids:tuple[str,...]
class CanonicalRetrievalBridge:
 def __init__(self,index,ledger,chunker,*,registry:DurableIngestionRegistry|None=None,outbox:IngestionOutbox|None=None,owner="retrieval",lease_ttl=60.0):
  self.index=index;self.ledger=ledger;self.chunker=chunker;self.registry=registry;self.outbox=outbox;self.owner=owner;self.lease_ttl=lease_ttl;self._receipts={}
 def _key(self,doc,decision):return f"{doc.content_hash}:{decision.decision_id}"
 @staticmethod
 def _receipt(raw):return RetrievalBridgeReceipt(raw["content_hash"],raw["chunks"],raw["index_revision"],tuple(raw["provenance_entry_ids"]))
 def ingest(self,doc:CrawlDocument,decision:PromotionDecision,*,now:float=0.0)->RetrievalBridgeReceipt:
  if decision.action!="promote" or decision.content_hash!=doc.content_hash:raise ValueError("retrieval admission requires matching promotion")
  key=self._key(doc,decision)
  if key in self._receipts:return self._receipts[key]
  lease=None
  if self.registry:
   reservation=self.registry.reserve(key,self.owner,now=now,ttl=self.lease_ttl)
   if isinstance(reservation,dict):return self._receipt(reservation)
   if reservation is None:raise RuntimeError("retrieval ingestion already reserved")
   lease=reservation
  try:
   chunks=tuple(self.chunker.chunk(doc.content_hash,doc.text))
   if len({x.chunk_id for x in chunks})!=len(chunks):raise ValueError("duplicate chunk ids")
   payloads=[{"chunk_id":x.chunk_id,"text":x.text,"start":x.start,"end":x.end} for x in chunks]
   operations=self.outbox.plan(key,payloads) if self.outbox else ()
   ids=[]
   for ordinal,chunk in enumerate(chunks):
    self.index.add(chunk.chunk_id,chunk.text)
    entry=self.ledger.record(source=doc.canonical_url,operation="crawler.promoted_chunk",
     input_data=doc.content_hash,output_data=chunk.text,
     metadata={"content_hash":doc.content_hash,"chunk_id":chunk.chunk_id,"start":chunk.start,"end":chunk.end,"promotion_decision_id":decision.decision_id},
     idempotency_key=operations[ordinal].operation_id if operations else None)
    ids.append(entry.entry_id)
    if operations:self.outbox.complete(operations[ordinal].operation_id,{"entry_id":entry.entry_id})
   receipt=RetrievalBridgeReceipt(doc.content_hash,len(chunks),self.index.revision,tuple(ids))
   if lease and not self.registry.complete(lease,asdict(receipt)):raise RuntimeError("lost retrieval ingestion lease")
   self._receipts[key]=receipt;return receipt
  except Exception:
   if lease:self.registry.abandon(lease)
   raise
