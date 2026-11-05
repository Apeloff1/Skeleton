"""Read-only persisted spine/custody inspection before claiming restart recovery."""
from __future__ import annotations
from .contracts import identifier,identity_hash,refuse

def inspect_restart(*,state_dir,tenant,subject,model_sha256,tokenizer_sha256):
    from skeleton.ai.runtime.operational_ai.deployment.boot.identity import PrincipalBinding,inspect_binding
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.doctor import inspect
    binding=PrincipalBinding(identifier(tenant),identifier(subject),
                  identity_hash(model_sha256),identity_hash(tokenizer_sha256))
    inspect_binding(state_dir,binding)
    with SpineDatabase(state_dir,readonly=True) as db:
        result=inspect(db)
    if type(result) is not dict:refuse("read-only durable integrity report missing")
    return {"state":"restart-storage-inspected-not-native-resumed",
            "doctor":result,"native_restart_e2e_proved":False}
