"""memory_dedup: rank — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.ranker import rank as rank_sources,RankedSource
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import identifier,refuse
def score(items,*,scope,limit=20):
    identifier(scope)
    if type(items) not in (tuple,list) or any(type(x) is not RankedSource for x in items):
        refuse("typed source evidence required")
    weights=(PROFILE.rank_lexical,PROFILE.rank_dense,PROFILE.rank_freshness)
    return rank_sources(items,scope=scope,weights=weights,limit=limit)
def highest(items,*,scope):
    result=score(items,scope=scope,limit=1)
    return result[0] if result else None
