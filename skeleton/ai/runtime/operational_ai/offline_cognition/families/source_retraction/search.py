"""source_retraction: search — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.retrieval import BM25,IndexedDocument
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import identifier,refuse
def query(documents,text,*,scope,limit=10):
    identifier(scope)
    if type(documents) not in (tuple,list) or not 1<=len(documents)<=10000:
        refuse("bounded source set required")
    if any(type(d) is not IndexedDocument for d in documents):
        refuse("source provenance must be typed")
    return BM25(documents).search(text,scope=scope,limit=limit)
def explain(results,*,scope):
    identifier(scope)
    return tuple({"source_id":k,"score":v,"scope":scope,
                  "source_text_authority":False} for k,v in results)
