"""history_projection: recover — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,refuse
from .replay import read
def reconcile(worker,scope,session_id,request_id,prompt):
    if type(scope) is not Scope:refuse("model-bound principal required")
    receipt=read(worker,scope,session_id,request_id,prompt)
    if receipt is None:
        return {"state":"native-effect-unknown","auto_retry":False,
                "reservation_released":False}
    return {"state":"spine-committed","output_sha256":receipt.output_sha256,
            "generated_again":False,"automatic_retry":False}
