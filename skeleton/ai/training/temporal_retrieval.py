"""Leakage-safe temporal retrieval and evidence qualification."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import TemporalSignalError
from .temporal_facts import TemporalFact,snapshot_facts

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class TemporalQuery:
 query_id:str; subject:str; as_of_year:int; mode:str; query_digest:str; max_results:int=32
 def __post_init__(self):
  if self.mode not in {"historical","current","extrapolation"}: raise TemporalSignalError("invalid temporal query mode")
  _hex(self.query_digest,"query")
  if not isinstance(self.max_results,int) or not 1<=self.max_results<=256: raise TemporalSignalError("invalid result budget")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalRetrievalReceipt:
 query_digest:str; snapshot_digest:str; result_fact_digests:tuple[str,...]; excluded_future_count:int
 mode:str; leakage_free:bool
 def __post_init__(self):
  _hex(self.query_digest,"query"); _hex(self.snapshot_digest,"snapshot")
  if tuple(sorted(self.result_fact_digests))!=self.result_fact_digests: raise TemporalSignalError("retrieval results not canonical")
  if len(set(self.result_fact_digests))!=len(self.result_fact_digests): raise TemporalSignalError("duplicate temporal retrieval result")
  if self.leakage_free is not True: raise TemporalSignalError("temporal retrieval must be leakage-free")
 @property
 def digest(self): return _digest(self.__dict__)

def retrieve_temporal_facts(facts,query):
 facts=tuple(facts)
 if any(f.subject!=query.subject for f in facts): raise TemporalSignalError("cross-subject retrieval contamination")
 if query.mode=="extrapolation": raise TemporalSignalError("extrapolation cannot retrieve unobserved facts as evidence")
 snap=snapshot_facts(facts,as_of_year=query.as_of_year)
 result=snap.fact_digests[:query.max_results]
 return TemporalRetrievalReceipt(query.digest,snap.digest,result,snap.excluded_future_count,query.mode,True)

@dataclass(frozen=True)
class TemporalEvidenceQualification:
 retrieval_digest:str; temporal_authority_digest:str; minimum_sources:int; source_count:int; qualified:bool
 @property
 def digest(self): return _digest(self.__dict__)

def qualify_temporal_retrieval(receipt,facts,*,temporal_authority_digest,min_sources=2):
 _hex(temporal_authority_digest,"temporal authority")
 by_digest={f.digest:f for f in facts}; selected=[by_digest[d] for d in receipt.result_fact_digests if d in by_digest]
 if len(selected)!=len(receipt.result_fact_digests): raise TemporalSignalError("retrieval receipt references unavailable fact")
 sources={f.source_digest for f in selected}
 if len(sources)<min_sources: raise TemporalSignalError("insufficient independent temporal sources")
 return TemporalEvidenceQualification(receipt.digest,temporal_authority_digest,min_sources,len(sources),True)

__all__=["TemporalQuery","TemporalRetrievalReceipt","TemporalEvidenceQualification","retrieve_temporal_facts","qualify_temporal_retrieval"]
