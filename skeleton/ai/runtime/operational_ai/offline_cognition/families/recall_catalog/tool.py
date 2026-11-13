"""recall_catalog: tool — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.tool_intents import ToolIntent,propose,inspect
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,refuse
def request(scope,*,request_id,tool,args,expires_ns):
    if type(scope) is not Scope:refuse("tenant/model-bound tool proposal required")
    return propose(scope,request_id=request_id,tool=tool,
                   arguments=args,expires_ns=expires_ns)
def status(intent,scope,*,now_ns):
    if type(intent) is not ToolIntent:refuse("source tool intent missing")
    return inspect(intent,scope,now_ns=now_ns,tool=intent.tool)
def model_can_execute():
    return False
