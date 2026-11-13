"""stream_commit: memory — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.memory import MemoryCatalog
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,refuse
def remember(store,scope,source_id,source_sha256,*,length,now_ns,expires_ns):
    if type(store) is not MemoryCatalog or type(scope) is not Scope:
        refuse("private tenant-scoped memory source required")
    return store.remember(scope,source_id,source_sha256,length=length,
                          now_ns=now_ns,consent_until_ns=expires_ns)
def recall(store,scope,*,now_ns,limit=20):
    if type(store) is not MemoryCatalog:refuse("private catalog required")
    return store.list(scope,now_ns=now_ns,limit=limit)
def forget(store,scope,source_id,*,revision,now_ns):
    if type(store) is not MemoryCatalog:refuse("private catalog required")
    return store.tombstone(scope,source_id,expected_revision=revision,now_ns=now_ns)
