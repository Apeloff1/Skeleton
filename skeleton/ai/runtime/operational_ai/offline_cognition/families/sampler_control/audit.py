"""sampler_control: audit — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.audit import Audit
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
def append(ledger,event,payload):
    if type(ledger) is not Audit:refuse("real hash chain required")
    return ledger.record(event,payload)
def verify(ledger):
    if type(ledger) is not Audit:refuse("auditable source record required")
    return {**ledger.verify(),"domain":PROFILE.name,
            "external_operator_signature_verified":False}
