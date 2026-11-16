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



def test_real_reviewed_feedback_trains_separate_native_candidate(tmp_path):
    from hashlib import sha256
    from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
    from skeleton.app.offline_http import OfflineHTTPApplication
    from scripts.train_jeeves_feedback_candidate import train_export, validate_export
    runtime=NativeLLMRuntime(TinyTransformer(
        vocab=("system:","user:","assistant:","red","blue","green","yellow","."," "),
        dim=8,ctx=128,n_heads=2,n_layers=1,seed=6),
        device_policy=DevicePolicy(requested="torch-cpu",allow_fallback=False))
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime),tmp_path/"training.sqlite3",token="t"*64)
    try:
        sid=app.dispatch("POST","/v1/sessions",{})[1]["session_id"]
        route="/v1/sessions/"+sid
        for i,question in enumerate(("red blue","green yellow")):
            app.dispatch("POST",route+"/turn",{"message":question,"request_id":"train-"+str(i),
                                              "max_output_tokens":2})
        saved=app.dispatch("GET",route)[1]
        rows=[r for r in saved["messages"] if r["role"]!="system"]
        for i,correction in enumerate(("red blue red blue","green yellow blue yellow")):
            q,a=rows[i*2:i*2+2]
            app.dispatch("POST",route+"/feedback-save",{
                "feedback_id":"review-"+str(i),"expected_revision":saved["revision"],
                "turn_index":i,"prompt_sha256":sha256(q["content"].encode()).hexdigest(),
                "answer_sha256":sha256(a["content"].encode()).hexdigest(),
                "preference":"corrected","correction":correction,"training_allowed":True,
                "rights_evidence_sha256":"a"*64,"approved":True})
        export=app.dispatch("POST",route+"/feedback-export",{
            "dataset_id":"reviewed","expected_revision":saved["revision"],
            "training_ids":["review-0"],"heldout_ids":["review-1"],"approved":True})[1]
        validate_export(export)
        from skeleton.app.jeeves_reviewed_feedback import _digest
        changed=dict(export,train=["unapproved replacement"])
        changed["export_sha256"]=_digest({k:v for k,v in changed.items() if k!="export_sha256"})
        with pytest.raises(TrainingContractError):
            validate_export(changed)
        initial=runtime.model_digest
        candidate=train_export(runtime,export,run_id="reviewed-native-candidate",
            targets=("layers.0.Wq",),policy=SpecializationPolicy(rank=2,steps=8))
        assert candidate["activation_authorized"] is False
        assert runtime.model_digest==initial
        assert candidate["dataset_revision_digest"]==export["dataset_revision_digest"]
        assert any(value!=0 for row in candidate["targets"]["layers.0.Wq"]["B"] for value in row)
        assert app.dispatch("GET",route)[1]==saved
    finally:
        app.close()
