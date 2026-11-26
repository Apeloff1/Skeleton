"""Actual native HTTP, durable batch and feedback regression coverage."""
from hashlib import sha256
import json

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.app.jeeves_reviewed_feedback import _digest
from skeleton.app.jeeves_review_campaign import CampaignConflict
from scripts.train_jeeves_feedback_candidate import validate_export


def _model():
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:","user:","assistant:","hello","world","answer","local",
               "offline","jeeves","computer","."," "),
        dim=8,ctx=1024,seed=41,n_heads=2,n_layers=2,d_ff=16,
    )))


def _session(app):
    _,result=app.dispatch("POST","/v1/sessions",{})
    return result["session_id"],"/v1/sessions/"+result["session_id"]


def _step(name,parents=()):
    return {"id":name,"depends_on":list(parents),"message":"hello",
            "max_output_tokens":4,"adaptive":{"max_attempts":1,
                "maximum_reserved_tokens":4,"language":"auto","contract":{"kind":"review"}}}


def _graph(app,route):
    return app.dispatch("POST",route+"/campaign-create",{
        "campaign_id":"flow","expected_session_revision":0,"approved":True,
        "steps":[_step("second",("first",)),_step("first"),_step("third",("second",))],
        "maximum_reserved_tokens":12})[1]


def _batch(graph,**changes):
    return {"campaign_id":"flow","batch_id":"batch-a","plan_sha256":graph["plan_sha256"],
            "expected_revision":graph["revision"],"steps":["first","second"],
            "maximum_reserved_tokens":8,"maximum_seconds":180,"approved":True}|changes


def test_approved_batch_executes_real_native_and_is_idempotent_after_restart(tmp_path):
    path=tmp_path/"campaign.sqlite3"
    app=OfflineHTTPApplication(_model(),path,token="t"*64)
    try:
        sid,route=_session(app)
        graph=_graph(app,route)
        request=_batch(graph)
        before=app.dispatch("GET",route)[1]
        _,result=app.dispatch("POST",route+"/campaign-batch-run",request)
        assert result["replayed"] is False
        assert result["batch"]["status"]=="complete"
        assert result["batch"]["completed"]==["first","second"]
        assert result["campaign"]["ready_steps"]==["third"]
        assert result["campaign"]["reserved_tokens"]==8
        assert result["campaign"]["revision"]==4
        assert result["campaign"]["statuses"]["first"]["report"]["generation_performed"] is True
        assert result["campaign"]["statuses"]["second"]["report"]["generation_performed"] is True
        assert app.dispatch("GET",route)[1]==before
    finally:
        app.close()
    app=OfflineHTTPApplication(_model(),path,token="t"*64)
    try:
        _,replay=app.dispatch("POST",route+"/campaign-batch-run",request)
        assert replay["replayed"] is True
        assert replay["batch"]==result["batch"]
        assert replay["campaign"]["reserved_tokens"]==8
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/campaign-batch-run",request|{"maximum_seconds":20})
        assert exc.value.status==409
        assert app.dispatch("GET",route)[1]==before
    finally:
        app.close()


@pytest.mark.parametrize("changes,status",[
    ({"approved":False},403),({"steps":["second","first"]},409),
    ({"steps":["first","first"]},400),({"maximum_reserved_tokens":7},409),
    ({"plan_sha256":"0"*64},409),({"expected_revision":1},409),
    ({"maximum_seconds":181},400),
])
def test_batch_rejects_unapproved_mutated_or_excess_work(tmp_path,changes,status):
    app=OfflineHTTPApplication(_model(),tmp_path/"denied.sqlite3",token="t"*64)
    try:
        sid,route=_session(app)
        graph=_graph(app,route)
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/campaign-batch-run",_batch(graph,**changes))
        assert exc.value.status==status
        assert app.review_campaigns.inspect(sid,"flow")["reserved_tokens"]==0
    finally:
        app.close()


def test_batch_interrupted_claim_is_inspect_only_and_explicit_abandon(tmp_path):
    path=tmp_path/"interrupted.sqlite3"
    app=OfflineHTTPApplication(_model(),path,token="t"*64)
    try:
        sid,route=_session(app)
        graph=_graph(app,route)
        request=_batch(graph)
        approval={k:v for k,v in request.items() if k not in {"campaign_id","approved"}}
        row,created=app.campaign_batches.begin(sid,"flow",approval)
        assert created and row["status"]=="running"
    finally:
        app.close()
    app=OfflineHTTPApplication(_model(),path,token="t"*64)
    try:
        _,replayed=app.dispatch("POST",route+"/campaign-batch-run",request)
        assert replayed["replayed"] is True
        assert replayed["batch"]["status"]=="running"
        assert replayed["campaign"]["reserved_tokens"]==0
        _,abandoned=app.dispatch("POST",route+"/campaign-batch-abandon",{
            "campaign_id":"flow","batch_id":"batch-a","approval_sha256":row["approval_sha256"],
            "approved":True})
        assert abandoned["batch"]["status"]=="abandoned_unconfirmed"
        assert app.dispatch("POST",route+"/campaign-batch-run",request)[1]["batch"]==abandoned["batch"]
    finally:
        app.close()


def _turns(app,route,prompts=("hello world","hello offline","computer local")):
    for i,prompt in enumerate(prompts):
        app.dispatch("POST",route+"/turn",{"message":prompt,"request_id":f"learning-turn-{i}",
                                           "max_output_tokens":2})
    saved=app.dispatch("GET",route)[1]
    return saved["revision"],[r for r in saved["messages"] if r["role"]!="system"]


def _feedback(revision,rows,index,**changes):
    prompt,answer=rows[index*2:index*2+2]
    return {"feedback_id":"review-"+str(index),"expected_revision":revision,
            "turn_index":index,"prompt_sha256":sha256(prompt["content"].encode()).hexdigest(),
            "answer_sha256":sha256(answer["content"].encode()).hexdigest(),
            "preference":"corrected","correction":"hello world" if index==0 else "offline local",
            "training_allowed":True,"rights_evidence_sha256":"a"*64,"approved":True}|changes


def test_feedback_export_uses_exact_approved_source_and_current_holdout_split(tmp_path):
    path=tmp_path/"feedback.sqlite3"
    app=OfflineHTTPApplication(_model(),path,token="t"*64)
    try:
        sid,route=_session(app)
        revision,rows=_turns(app,route)
        first=_feedback(revision,rows,0)
        second=_feedback(revision,rows,1)
        assert app.dispatch("POST",route+"/feedback-save",first)[0]==201
        assert app.dispatch("POST",route+"/feedback-save",first)[0]==200
        assert app.dispatch("POST",route+"/feedback-save",second)[0]==201
        app.dispatch("POST",route+"/feedback-save",_feedback(revision,rows,2,
            preference="rejected",correction="",training_allowed=False,rights_evidence_sha256=None))
        body={"dataset_id":"local-feedback","expected_revision":revision,
              "training_ids":["review-0"],"heldout_ids":["review-1"],"approved":True}
        _,export=app.dispatch("POST",route+"/feedback-export",body)
        rights,dataset,train,heldout=validate_export(export)
        assert rights.permits("specialization")
        assert train==["user: hello world\nassistant: hello world"]
        assert heldout==["user: hello offline\nassistant: offline local"]
        assert export["training_performed"] is False
        assert export["activation_authorized"] is False
        assert export["export_sha256"]==_digest({k:v for k,v in export.items() if k!="export_sha256"})
        assert dataset.digest==export["dataset_revision_digest"]
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/feedback-export",body|{"heldout_ids":["review-2"]})
        assert exc.value.status==400
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/feedback-export",body|{"heldout_ids":["review-0"]})
        assert exc.value.status==400
    finally:
        app.close()
    app=OfflineHTTPApplication(_model(),path,token="t"*64)
    try:
        _,listed=app.dispatch("POST",route+"/feedback-list",{})
        assert len(listed["examples"])==3
        assert app.dispatch("POST",route+"/feedback-export",body)[1]==export
        row=listed["examples"][0]
        app.dispatch("POST",route+"/feedback-delete",{"feedback_id":row["feedback_id"],
            "expected_sha256":row["feedback_sha256"],"approved":True})
        with pytest.raises(OfflineHTTPError):
            app.dispatch("POST",route+"/feedback-export",body)
        app.dispatch("DELETE",route)
        assert app._store._db.execute("SELECT COUNT(*) FROM offline_reviewed_feedback").fetchone()==(0,)
    finally:
        app.close()


@pytest.mark.parametrize("changes,status",[
    ({"approved":False},403),({"answer_sha256":"0"*64},409),
    ({"expected_revision":0},400),({"expected_revision":99},409),
    ({"training_allowed":True,"rights_evidence_sha256":None},400),
    ({"preference":"rejected","correction":""},400),
    ({"preference":"preferred"},400),
])
def test_feedback_rejects_bad_source_or_training_permission(tmp_path,changes,status):
    app=OfflineHTTPApplication(_model(),tmp_path/"denied.sqlite3",token="t"*64)
    try:
        sid,route=_session(app)
        revision,rows=_turns(app,route,("hello",))
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/feedback-save",_feedback(revision,rows,0,**changes))
        assert exc.value.status==status
        assert app.dispatch("POST",route+"/feedback-list",{})[1]["examples"]==[]
    finally:
        app.close()


def test_feedback_export_duplicate_normalized_prompts_fail_closed(tmp_path):
    app=OfflineHTTPApplication(_model(),tmp_path/"duplicates.sqlite3",token="t"*64)
    try:
        sid,route=_session(app)
        revision,rows=_turns(app,route,("hello","HELLO"))
        for i in range(2):
            app.dispatch("POST",route+"/feedback-save",_feedback(revision,rows,i))
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/feedback-export",{"dataset_id":"duplicates",
                "expected_revision":revision,"training_ids":["review-0"],
                "heldout_ids":["review-1"],"approved":True})
        assert exc.value.status==400
    finally:
        app.close()


def test_browser_advanced_controls_and_private_draft_scrubbing():
    from skeleton.app.offline_web import HTML,JAVASCRIPT,CSS
    for element in ("advanced-reasoning-options","learned-review","campaign-batch-panel",
                    "campaign-batch-run","feedback-panel","feedback-export"):
        assert f'id="{element}"' in HTML
    assert 'id="advanced-reasoning-options" class="advanced-reasoning-options">' in HTML
    assert "get('advanced-reasoning-options').open = false;" in JAVASCRIPT
    assert "get('feedback-correction').value=''" in JAVASCRIPT
    assert "Batch outcome unconfirmed" in JAVASCRIPT
    assert "Independent local NLI review" in JAVASCRIPT
    assert ".advanced-reasoning-options[open]" in CSS
