"""Fail-closed handoff from gathered evidence to retrieval/training consumers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol,Mapping
from .core import CrawlDocument
from .governance import PromotionDecision

class RetrievalSink(Protocol):
    def upsert(self,record:Mapping[str,object])->None: ...

@dataclass(frozen=True)
class IngestionReceipt:
    content_hash:str; destination:str; accepted:bool; reason:str
    def as_dict(self):return {"schema":"skeleton.ai.crawl.ingestion.v1",**self.__dict__}

class GovernedIngestor:
    def __init__(self,sink:RetrievalSink,destination="retrieval"):
        self.sink=sink;self.destination=destination
    def ingest(self,doc:CrawlDocument,decision:PromotionDecision)->IngestionReceipt:
        if decision.content_hash != doc.content_hash:
            return IngestionReceipt(doc.content_hash,self.destination,False,"decision_content_mismatch")
        if decision.action != "promote":
            return IngestionReceipt(doc.content_hash,self.destination,False,"not_promoted")
        record=doc.retrieval_record()
        metadata=dict(record["metadata"])
        metadata["promotion_receipt"]=decision.receipt()
        record["metadata"]=metadata
        self.sink.upsert(record)
        return IngestionReceipt(doc.content_hash,self.destination,True,"promoted")
