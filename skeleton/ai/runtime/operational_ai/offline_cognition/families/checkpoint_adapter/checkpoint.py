"""checkpoint_adapter: checkpoint — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.audit import Audit
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,sha,fingerprint,refuse
def capture(audit,scope,source_sha256):
    if type(audit) is not Audit or type(scope) is not Scope:
        refuse("typed checkpoint actor/chain required")
    chain=audit.verify()
    claim={"scope_sha256":scope.digest(),"source_sha256":sha(source_sha256),
           "audit_head":chain["head_sha256"],"event_count":chain["count"],
           "domain":PROFILE.name}
    return {**claim,"sha256":fingerprint(claim),
            "external_checkpoint_signature":False}
