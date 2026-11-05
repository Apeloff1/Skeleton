"""recall_catalog: fusion — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.retrieval import hybrid
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import identifier
def combine(lexical,dense,*,scope,limit=10):
    identifier(scope)
    if PROFILE.retrieval_mode=="lexical":dense=()
    elif PROFILE.retrieval_mode=="dense":lexical=()
    return hybrid(lexical,dense,scope=scope,max_results=limit)
def describe(results):
    return {"domain":PROFILE.name,"method":PROFILE.retrieval_mode,
            "sources":tuple(results),"operator_rights_inferred":False}
