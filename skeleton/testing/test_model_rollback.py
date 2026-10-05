from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.deployment_operations_assurance import (
    DeploymentOperationsAssuranceError, ModelRollbackFence, qualify_model_rollback,
)
from skeleton.ai.runtime.deferred.operations_experience import ModelOperations, ModelRevision

A="a"*64
B="b"*64
C="c"*64
D="d"*64
E="e"*64
F="f"*64

def test_model_rollback_is_version_and_active_artifact_fenced()->None:
    active=ModelRevision("model",2,A,B,"active")
    target=ModelRevision("model",1,C,D,"qualified")
    fence=ModelRollbackFence("model",2,1,E,A,F)
    evidence=qualify_model_rollback(
        ModelOperations(),fence,active_revision=active,target_revision=target,
    )
    assert evidence.eligible is True
    assert evidence.target_artifact_digest==C
    assert evidence.reason_code=="qualified-target"
    assert evidence.production_authority is False

def test_model_rollback_rejects_active_artifact_mismatch()->None:
    active=ModelRevision("model",2,A,B,"active")
    target=ModelRevision("model",1,C,D,"qualified")
    with pytest.raises(DeploymentOperationsAssuranceError,match="artifact fence"):
        qualify_model_rollback(
            ModelOperations(),ModelRollbackFence("model",2,1,E,"0"*64,F),
            active_revision=active,target_revision=target,
        )
