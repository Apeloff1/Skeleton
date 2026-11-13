"""tenant_compartment: native — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.engine import CognitiveEngine
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,text,refuse
def generate(worker,scope,session_id,request_id,prompt,*,seed=0,temperature=0.8):
    if type(scope) is not Scope:refuse("typed model principal required")
    text(prompt,maximum=min(PROFILE.byte_limit,32768))
    # Exactly one call through the existing real SupervisedAI inference spine.
    return CognitiveEngine(scope,worker).turn(session_id,request_id,prompt,
                                               seed=seed,temperature=temperature)
def probe(worker,scope):
    CognitiveEngine(scope,worker)
    return {"model_bound":True,"scope_sha256":scope.digest(),
            "live_native_model_proved_by_probe":False}
