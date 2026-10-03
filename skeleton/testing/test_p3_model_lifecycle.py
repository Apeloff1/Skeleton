from __future__ import annotations
import hashlib,json
import pytest
from skeleton.ai.runtime.learning_foundation.lifecycle import ModelBillOfMaterials,ModelLifecycleError,ModelLifecycleRegistry,ModelLifecycleState
from skeleton.learning.model_program import ModelArtifact,TrainingReceipt

def _sha(value:str)->str:return hashlib.sha256(value.encode()).hexdigest()

def _parts(model_id:str,seed:int):
    payload={"kind":"fixture","seed":seed}
    ad=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    md=_sha(f"{model_id}:{seed}")
    artifact=ModelArtifact(model_id=model_id,model_digest=md,artifact_digest=ad,kind="fixture",payload=payload,training_run_id=f"run-{seed}")
    receipt=TrainingReceipt(run_id=f"run-{seed}",spec_digest=_sha(f"spec-{seed}"),dataset_digests=(_sha(f"dataset-{seed}"),),trainer_id=f"trainer-{seed}",code_revision=f"rev-{seed}",model_id=model_id,model_digest=md,artifact_digest=ad,metrics={"loss":0.1})
    return artifact,receipt

def _mbom(model_id:str,seed:int):
    a,r=_parts(model_id,seed)
    return ModelBillOfMaterials.from_training(a,r,license_refs=("license:apache-2.0",),rights_refs=("rights:train-eval-deploy",),dependency_refs=(f"runtime:local:{seed}",))

def test_mbom_binds_training_and_rights_identity():
    left=_mbom("model-a",1);right=_mbom("model-a",1)
    assert left==right and left.digest==right.digest
    assert left.license_refs==("license:apache-2.0",)
    assert left.rights_refs==("rights:train-eval-deploy",)

def test_lifecycle_requires_independent_validation():
    registry=ModelLifecycleRegistry();mbom=registry.register_candidate(_mbom("model-a",1))
    with pytest.raises(ModelLifecycleError,match="trainer cannot independently"):
        registry.transition(mbom.model_digest,ModelLifecycleState.VALIDATED,verifier_id=mbom.trainer_id,evidence_refs=("eval:a","eval:b"))
    registry.transition(mbom.model_digest,ModelLifecycleState.VALIDATED,verifier_id="independent-verifier",evidence_refs=("eval:a","eval:b"))
    registry.transition(mbom.model_digest,ModelLifecycleState.ACTIVE,verifier_id="release-verifier",evidence_refs=("canary:a","rollback:a"))
    assert registry.state(mbom.model_digest) is ModelLifecycleState.ACTIVE

def test_migration_is_parity_gated_with_rollback():
    registry=ModelLifecycleRegistry();source=registry.register_candidate(_mbom("source",1));target=registry.register_candidate(_mbom("target",2))
    registry.transition(source.model_digest,ModelLifecycleState.VALIDATED,verifier_id="v1",evidence_refs=("e:a","e:b"))
    registry.transition(source.model_digest,ModelLifecycleState.ACTIVE,verifier_id="v2",evidence_refs=("c:a","r:a"))
    registry.transition(target.model_digest,ModelLifecycleState.VALIDATED,verifier_id="v3",evidence_refs=("e:c","e:d"))
    denied=registry.migration_decision(source_model_digest=source.model_digest,target_model_digest=target.model_digest,parity_score=.89,required_score=.95,verifier_id="migration-v",evaluation_refs=("p:a","p:b"))
    assert denied.approved is False and denied.rollback_model_digest==source.model_digest
    approved=registry.migration_decision(source_model_digest=source.model_digest,target_model_digest=target.model_digest,parity_score=.98,required_score=.95,verifier_id="migration-v",evaluation_refs=("p:a","p:b"))
    assert approved.approved is True

def test_mbom_rejects_missing_rights():
    a,r=_parts("model-a",3)
    with pytest.raises(ModelLifecycleError,match="rights_ref requires at least"):
        ModelBillOfMaterials.from_training(a,r,license_refs=("license:apache-2.0",),rights_refs=())
