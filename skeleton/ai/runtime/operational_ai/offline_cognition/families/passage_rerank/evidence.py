"""passage_rerank: typed original-source retrieval over the shared finite evidence engine.

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
    """Choose a bounded overlap for smaller source windows by default.

    Explicit overlap is never silently clamped: the shared original-byte
    partitioner retains its full finite window/overlap validation. The
    default preserves 128-byte overlap for ordinary 2048-byte passages
    and scales down to a quarter-window for source/quote slices.
    """
    if overlap_bytes is None:
        if type(window_bytes) is int and 16 <= window_bytes <= 65536:
            overlap_bytes=min(128,window_bytes//4)
        else:
            overlap_bytes=128
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
