"""system_policy: permission — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.admission import Permit,admit
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,refuse
def inspect(permit,scope,*,operation,now_ns,source_sha256):
    if type(permit) is not Permit or type(scope) is not Scope:
        refuse("operator-bound source permit required")
    return admit(permit,scope,operation,now_ns=now_ns,
                 required_source_sha256=source_sha256)
def external_approval_verified():
    return False
