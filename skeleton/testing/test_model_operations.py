from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import register_model_operation
from skeleton.ai.runtime.deferred.operations_experience import ModelOperations, ModelRevision

A="a"*64
B="b"*64
C="c"*64
D="d"*64

def test_model_operations_bind_router_and_release_gates()->None:
    registry=ModelOperations()
    evidence=register_model_operation(
        registry,ModelRevision("model",1,A,B,"qualified"),
        router_gate_digest=C,release_gate_digest=D,
    )
    assert evidence.eligible_for_activation is True
    assert evidence.router_gate_digest==C
    assert evidence.release_gate_digest==D
    assert evidence.production_authority is False

def test_unqualified_model_is_registered_but_not_activation_eligible()->None:
    evidence=register_model_operation(
        ModelOperations(),ModelRevision("model",1,A,B,"candidate"),
        router_gate_digest=C,release_gate_digest=D,
    )
    assert evidence.eligible_for_activation is False
