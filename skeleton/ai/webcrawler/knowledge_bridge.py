"""Adapters into Skeleton's canonical evidence-bound knowledge contract."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from .core import CrawlDocument
from .governance import PromotionDecision

@dataclass(frozen=True)
class KnowledgeBridgeReceipt:
 claim_id:str;identity:str;content_hash:str;verification:str

class CanonicalKnowledgeBridge:
 """Records a promoted crawled document as evidence-bound source knowledge.

 Imports are lazy so the crawler remains usable as an isolated plane, while production
 handoff uses the canonical runtime contract rather than a parallel store.
 """
 def __init__(self,store,*,scope_key="web-research"):
  self.store=store;self.scope_key=scope_key
 def record_document(self,doc:CrawlDocument,decision:PromotionDecision,*,subject:str|None=None):
  if decision.action!="promote" or decision.content_hash!=doc.content_hash:
   raise ValueError("canonical knowledge admission requires matching promotion")
  if decision.required_sources < 1 or decision.qualified_sources < decision.required_sources:
   raise ValueError("corroborated knowledge requires qualified independent sources")
  from skeleton.ai.runtime.knowledge.store import (
   KnowledgeClaim,KnowledgeEvidence,VerificationState,
  )
  evidence=KnowledgeEvidence(doc.canonical_url,doc.content_hash,doc.fetched_at)
  claim_id=hashlib.sha256(
   f"crawl:{self.scope_key}:{doc.canonical_url}:{doc.content_hash}".encode()
  ).hexdigest()
  claim=KnowledgeClaim(
   claim_id=claim_id,scope_key=self.scope_key,subject=subject or doc.canonical_url,
   predicate="document_content_digest",value_digest=doc.content_hash,
   confidence=decision.assurance_score,
   verification=VerificationState.CORROBORATED,
   evidence=(evidence,),recorded_at=decision.decided_at,
  )
  identity=self.store.record(claim)
  return KnowledgeBridgeReceipt(claim_id,identity,doc.content_hash,claim.verification.value)
