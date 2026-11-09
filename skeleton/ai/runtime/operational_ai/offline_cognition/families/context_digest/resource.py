"""context_digest: resource — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.budget import Resource,reserve_batch,partition
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import integer,refuse
def reserve(capacity,candidates):
    if type(capacity) is not Resource or capacity.tokens>PROFILE.context_limit*16:
        refuse("resource observation or ceiling invalid")
    return reserve_batch(capacity,candidates)
def allocate(total,weights):
    integer(total,maximum=PROFILE.context_limit*16)
    return partition(total,weights)
def sufficient(observed,required):
    if type(observed) is not Resource or type(required) is not Resource:
        refuse("typed measured device resources required")
    return {"admitted":required.fits(observed),"device_certified":False}
