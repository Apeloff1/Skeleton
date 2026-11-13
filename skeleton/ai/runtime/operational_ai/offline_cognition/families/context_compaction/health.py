"""context_compaction: health — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.budget import Resource
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import integer,refuse
def resources(observed,required):
    if type(observed) is not Resource or type(required) is not Resource:
        refuse("measured physical capacity required")
    return {"admitted":required.fits(observed),"domain":PROFILE.name,
            "laptop_device_qualified":False}
def status(ready,source_verified,rights_approved,failures):
    if any(type(x) is not bool for x in (ready,source_verified,rights_approved)):
        refuse("explicit external evidence needed")
    integer(failures,maximum=1000000)
    return {"healthy_claim":ready and source_verified and rights_approved and failures==0,
            "native_model_e2e":False,"release_certified":False}
