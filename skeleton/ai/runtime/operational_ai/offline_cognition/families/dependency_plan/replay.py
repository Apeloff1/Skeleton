"""provenance_refresh: replay — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.receipts import from_supervisor
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,identifier,text,refuse
def read(worker,scope,session_id,request_id,prompt,*,seed=0,temperature=0.8):
    if type(scope) is not Scope:refuse("typed replay identity required")
    # Read-only durable output still requires exact active principal and model.
    from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
    try:
        active=ActiveModel.from_supervisor(worker)
    except (AttributeError,ValueError,TypeError):
        refuse("canonical supervised replay owner required")
    if (active.tenant,active.subject,active.model_sha256,
        active.tokenizer_sha256)!=(scope.tenant,scope.subject,
        scope.model_sha256,scope.tokenizer_sha256):
        refuse("foreign subject or model attempted durable replay")
    identifier(session_id);identifier(request_id)
    text(prompt,maximum=min(PROFILE.byte_limit,32768))
    record=worker.spine.replay(session_id,request_id,prompt,
                               seed=seed,temperature=temperature)
    if record is None:return None
    checked=from_supervisor(scope,session_id,request_id,record)
    if not checked.replayed:refuse("uncommitted replay claim")
    return checked
def unknown():
    return {"automatic_retry":False,"quota_refund":False}
