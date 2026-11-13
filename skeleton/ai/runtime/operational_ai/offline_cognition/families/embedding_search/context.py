"""provenance_refresh: context — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contexts import pack,sliding_history,ContextSlice
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
def assemble(slices,*,output_tokens=128):
    if type(slices) not in (tuple,list) or any(type(x) is not ContextSlice for x in slices):
        refuse("bounded typed context slices required")
    return pack(slices,window=PROFILE.context_limit,
                output_reserved=output_tokens,safety_reserved=32)
def history(rows,*,last_n=16):
    return sliding_history(rows,last_n=last_n,byte_budget=PROFILE.byte_limit)
def receipt():
    return {"context_ceiling":PROFILE.context_limit,
            "real_native_tokenizer_attested":False}
