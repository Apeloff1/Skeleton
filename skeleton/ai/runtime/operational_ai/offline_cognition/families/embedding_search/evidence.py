"""embedding_search: typed original-source retrieval over the shared finite evidence engine.

The source-bound operator entrypoints are deterministic; no native inference,
third-party rights proof or semantic entailment is implicitly authorized.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import (
    EvidenceIndex,EvidenceDocument,EvidenceSpan,partition,verify,diverse_spans,unique_spans,
)

def index(records,*,tenant,subject):
    if type(records) not in (tuple,list) or len(records)>2048:
        refuse("finite typed source inventory required")
    return EvidenceIndex(records,tenant=tenant,subject=subject)

def query(catalog,text,*,limit=10,query_vector=None,embedding_model_sha256=None):
    if type(catalog) is not EvidenceIndex:refuse("trusted evidence index required")
    return catalog.retrieve(text,mode=PROFILE.retrieval_mode,limit=limit,
                            query_vector=query_vector,
                            embedding_model_sha256=embedding_model_sha256)

def passages(document,*,window_bytes=2048,overlap_bytes=None):
    # Delegate implicit overlap selection to the shared bounded evidence engine.
    # Explicit invalid overlaps must still be rejected, never silently clamped.
    # Select a bounded overlap only when the caller leaves it implicit.
    # Preserve the shared core's explicit invalid-overlap rejection.
    if overlap_bytes is None:
        overlap_bytes=min(128,window_bytes//4) if type(window_bytes) is int and window_bytes>=16 else 0
    return partition(document,window_bytes=window_bytes,overlap_bytes=overlap_bytes)

def citation(catalog,span,*,quoted_text=None):
    if type(catalog) is not EvidenceIndex:refuse("trusted evidence index required")
    return catalog.cite(span,quoted_text=quoted_text)

def rank_candidates(rows,*,limit=10):
    return diverse_spans(rows,limit=limit)

def distinct(rows):
    return unique_spans(rows)

def report(catalog,spans):
    if type(catalog) is not EvidenceIndex:refuse("trusted evidence index required")
    return catalog.attribution(spans)

def contract():
    return {"family":PROFILE.name,"mode":PROFILE.retrieval_mode,
            "byte_limit":PROFILE.byte_limit,"context_ceiling":PROFILE.context_limit,
            "native_generation_executed":False,"rights_independently_proved":False,
            "semantic_entailment_proved":False}
