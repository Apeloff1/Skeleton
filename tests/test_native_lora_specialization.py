import pytest

torch=pytest.importorskip("torch")
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy
from skeleton.ai.training.flgb_training_runtime import AdapterTrainingRun, DatasetRevision, DatasetRights, TrainingContractError
from skeleton.ai.training.native_lora_specialization import (
    SpecializationPolicy, dataset_digest, train_specialization, materialize_candidate, publish_candidate,
)


def fixture():
    model=TinyTransformer({"red","blue","green","yellow"},dim=8,ctx=16,n_heads=2,n_layers=1,seed=6)
    runtime=NativeLLMRuntime(model,device_policy=DevicePolicy(requested="torch-cpu",allow_fallback=False))
    train=["red blue red blue","green blue green blue"]
    heldout=["yellow blue yellow blue"]
    policy=SpecializationPolicy(rank=2,steps=12,learning_rate=0.03)
    rights=DatasetRights("local","operator","allowed","owned",("specialization",),"a"*64)
    revision=DatasetRevision("local",0,dataset_digest(train,heldout),rights.digest,"b"*64)
    run=AdapterTrainingRun("fixture",runtime.model_digest,revision.digest,("Wout","layers.0.Wq"),policy.digest)
    return runtime,run,rights,revision,train,heldout,policy


def test_actual_adapter_gradient_and_separate_candidate(tmp_path):
    rt,run,rights,revision,train,heldout,policy=fixture()
    initial=rt.model_digest
    candidate=train_specialization(rt,run,rights,revision,train,heldout,scope="specialization",policy=policy)
    assert candidate["activation_authorized"] is False
    assert any(v!=0 for target in candidate["targets"].values() for row in target["B"] for v in row)
    clone,identity=materialize_candidate(rt,candidate,expected_sha256=candidate["candidate_sha256"])
    assert rt.model_digest==initial and clone.model_digest!=initial
    assert identity.production_authorized() is False
    path=tmp_path/"adapter.json"
    assert len(publish_candidate(candidate,path))==64 and path.exists()
    with pytest.raises(FileExistsError):
        publish_candidate(candidate,path)


def test_rights_and_contamination_fail_closed():
    rt,run,rights,revision,train,heldout,policy=fixture()
    with pytest.raises(TrainingContractError,match="authority"):
        train_specialization(rt,run,rights,revision,train,heldout,scope="different",policy=policy)
    revision=DatasetRevision("local",0,dataset_digest(train,train),rights.digest,"b"*64)
    run=AdapterTrainingRun("fixture",rt.model_digest,revision.digest,("Wout",),policy.digest)
    with pytest.raises(TrainingContractError,match="contamination"):
        train_specialization(rt,run,rights,revision,train,train,scope="specialization",policy=policy)
