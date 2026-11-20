"""Source qualification of the five-capability local runtime expansion.

The fixtures use actual native transformer weights, not mocked generators.
They establish execution parity and boundary behavior, not frontier quality.
"""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy,GenerationConfig,RuntimeContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer
from skeleton.app.local_ai import OfflineAISession
from skeleton.app.offline_http import OfflineHTTPApplication,OfflineHTTPError
from skeleton.app.jeeves_ensemble import SpecialistRegistry,digest
from skeleton.app.jeeves_speculative import generate_speculative
from skeleton.app.jeeves_prefetch import rank_questions


VOCAB=("system:","user:","assistant:","hello","world","answer","local",
       "offline","jeeves","computer","."," ")


def runtime(seed=41,vocab=VOCAB):
    return NativeLLMRuntime(TinyTransformer(vocab=vocab,dim=8,ctx=256,seed=seed,
        n_heads=2,n_layers=2,d_ff=16),device_policy=DevicePolicy(requested="cpu",allow_fallback=False))


def registry(tmp_path,models):
    profiles=[]
    for name,role,rt in models:
        path=tmp_path/(name+".json")
        raw=rt.checkpoint_json().encode()
        path.write_bytes(raw)
        profiles.append({"id":name,"role":role,"path":path.name,"file_sha256":sha256(raw).hexdigest(),
            "model_digest":rt.model_digest,"tokenizer_digest":rt.tokenizer.digest,"max_bytes":len(raw)})
    path=tmp_path/"specialists.json"
    raw=json.dumps({"schema":"skeleton.jeeves.specialists.v1","profiles":profiles}).encode()
    path.write_bytes(raw)
    return SpecialistRegistry(path,sha256(raw).hexdigest())


def session(app):
    created=app.dispatch("POST","/v1/sessions",{})[1]
    return created["session_id"],"/v1/sessions/"+created["session_id"]


@pytest.mark.parametrize("block",[1,2,4,8])
def test_speculative_real_draft_target_matches_serial_greedy_tokens(block):
    target,draft=runtime(),runtime(17)
    assert target.model_digest!=draft.model_digest
    assert target.tokenizer.digest==draft.tokenizer.digest
    cfg=GenerationConfig(max_new_tokens=10,temperature=0,use_cache=False)
    expected=target.generate("hello world",cfg)
    result=generate_speculative(target,draft,"hello world",cfg,block=block)
    assert result["generated_ids"]==list(expected.generated_ids)
    assert result["text"]==expected.text
    assert result["finish_reason"]==expected.finish_reason
    assert result["target_block_graph_calls"]<=cfg.max_new_tokens
    assert result["draft_graph_calls"]==result["proposed_tokens"]
    assert result["accepted_draft_tokens"]<=result["proposed_tokens"]
    assert result["target_authoritative"] is True
    assert result["speedup_certified"] is False
    assert len(result["receipt_sha256"])==64


def test_speculative_stop_and_policy_rejections():
    target,draft=runtime(),runtime(17)
    plain=target.generate("hello world",GenerationConfig(max_new_tokens=5,temperature=0,use_cache=False))
    cfg=GenerationConfig(max_new_tokens=5,temperature=0,use_cache=False,
                         stop_token_ids=(plain.generated_ids[0],),include_stop_tokens=False)
    result=generate_speculative(target,draft,"hello world",cfg)
    assert result["generated_ids"]==[plain.generated_ids[0]]
    assert result["finish_reason"]=="stop_token" and result["text"]==""
    with pytest.raises(RuntimeContractError):
        generate_speculative(target,target,"hello",cfg)
    with pytest.raises(RuntimeContractError):
        generate_speculative(target,runtime(17,VOCAB+("different",)),"hello",cfg)
    with pytest.raises(RuntimeContractError):
        generate_speculative(target,draft,"hello",GenerationConfig(max_new_tokens=2,temperature=1))


def test_registry_pins_exact_artifacts_and_distinct_generators(tmp_path):
    target,draft=runtime(),runtime(17)
    reg=registry(tmp_path,[("draft","draft",draft)])
    actual=reg.load("draft",primary_digest=target.model_digest,required_role="draft")
    assert actual.model_digest==draft.model_digest
    with pytest.raises(ValueError):
        reg.load("draft",primary_digest=draft.model_digest)
    with pytest.raises(ValueError):
        reg.load("draft",primary_digest=target.model_digest,required_role="coding")
    path=tmp_path/"draft.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises((ValueError,OSError)):
        reg.load("draft",primary_digest=target.model_digest)


def test_actual_ensemble_and_speculative_http_remain_ephemeral(tmp_path):
    target,draft,specialist=runtime(),runtime(17),runtime(42)
    config=registry(tmp_path,[("draft","draft",draft),("coder","coding",specialist)])
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(target),tmp_path/"chat.sqlite3",
        token="t"*64,specialist_registry=config)
    try:
        sid,route=session(app)
        before=app.dispatch("GET",route)[1]
        cap=app.dispatch("GET","/v1/competitive/status")[1]
        assert cap["native_greedy_speculative_target"] and len(cap["specialists"])==2
        question="hello world"
        payload={"expected_revision":0,"message":question,"profiles":["draft","coder"],
                 "max_output_tokens":6,"maximum_reserved_tokens":18,"approved":True}
        result=app.dispatch("POST",route+"/ensemble-review",payload)[1]
        assert result["independent_model_count"]==3
        assert [c["model_digest"] for c in result["candidates"]]==[
            target.model_digest,draft.model_digest,specialist.model_digest]
        assert all(c["output_sha256"]==sha256(c["text"].encode()).hexdigest()
                   for c in result["candidates"])
        assert result["reserved_output_tokens"]==18
        assert result["winner_selected"] is False
        assert result["receipt_sha256"]==digest({k:v for k,v in result.items() if k!="receipt_sha256"})
        review=app.dispatch("POST",route+"/speculative-review",{
            "expected_revision":0,"message":question,"draft_profile":"draft","max_output_tokens":6,
            "block":3,"approved":True})[1]
        request,_=OfflineAISession(app.backend)._request(question,6,require_full_history=True)
        baseline=target.generate(request.rendered_input,GenerationConfig(max_new_tokens=6,
            temperature=0,use_cache=False))
        assert review["generated_ids"]==list(baseline.generated_ids)
        assert app.dispatch("GET",route)[1]==before
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/ensemble-review",payload|{"maximum_reserved_tokens":17})
        assert exc.value.status==422
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/ensemble-review",payload|{"approved":False})
        assert exc.value.status==403
    finally:
        app.close()


def test_prediction_priority_exact_scoped_cache_and_normal_chat_consumption(tmp_path,monkeypatch):
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime()),tmp_path/"chat.sqlite3",token="t"*64)
    try:
        sid,route=session(app)
        doc=app.knowledge.add_text("harbor signal","The harbor signal is violet. The local radio is ready.")
        other=app.knowledge.add_text("excluded","The harbor signal is unrelated.")
        ranked=rank_questions([{"role":"user","content":"harbor signal violet"}],
                               ["unrelated weather","harbor signal"])
        assert ranked[0][2]=="harbor signal"
        before=app.dispatch("GET",route)[1]
        question="harbor signal"
        data={"expected_revision":0,"candidates":[question,"local radio"],"document_ids":[doc["document_id"]],
              "maximum_queries":2,"approved":True}
        warmed=app.dispatch("POST",route+"/predictive-prefetch",data)[1]
        assert len(warmed["warmed"])==2 and app.competitive.prefetch.stats()["entries"]==2
        assert app.dispatch("GET",route)[1]==before
        assert app.competitive.prefetch.consume(sid,1,question,[doc["document_id"]]) is None
        assert app.competitive.prefetch.consume(sid,0,question,[other["document_id"]]) is None
        other_sid,_=session(app)
        assert app.competitive.prefetch.consume(other_sid,0,question,[doc["document_id"]]) is None
        # Fail if live ranking is invoked: the actual normal grounded turn
        # must consume its exact prefetched result, not merely display cache metadata.
        def denied(*args,**kwargs):
            raise AssertionError("live ranking unexpectedly rerun")
        monkeypatch.setattr(app,"_grounding_hits",denied)
        result=app.dispatch("POST",route+"/turn",{"message":question,
            "request_id":"warm-turn","max_output_tokens":4,"grounded":True,
            "document_ids":[doc["document_id"]]})[1]
        assert result["revision"]==1
        assert app.competitive.prefetch.stats()["entries"]==1
        assert app.competitive.prefetch.consume(sid,1,"local radio",[doc["document_id"]]) is None
        app.knowledge.delete(doc["document_id"])
        with pytest.raises(RuntimeContractError):
            app.competitive.prefetch.consume(sid,0,"local radio",[doc["document_id"]])
        assert app.competitive.prefetch.stats()["entries"]==0
    finally:
        app.close()


def action(name,kind,args,depends=(),condition="always",source=None):
    return {"id":name,"kind":kind,"arguments":args,"depends_on":list(depends),
            "condition":{"kind":condition,"action":source}}


def test_actual_conditional_tool_campaign_execution_and_restart_idempotence(tmp_path):
    path=tmp_path/"chat.sqlite3"
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime()),path,token="t"*64)
    try:
        sid,route=session(app)
        doc=app.knowledge.add_text("reference","The harbor signal is violet.")
        before=app.dispatch("GET",route)[1]
        plan={"actions":[action("lookup","search",{"query":"harbor signal",
                "document_ids":[doc["document_id"]],"limit":2}),
            action("verify","document_identity",{"document_id":doc["document_id"],"sha256":doc["sha256"]},
                   ["lookup"],"has_hits","lookup"),
            action("skip","calculate",{"expression":"1+2"},["lookup"],"no_hits","lookup"),
            action("math","calculate",{"expression":"(17+5)*3/2"},["verify"])],
              "maximum_calls":3,"maximum_seconds":30}
        body={"campaign_id":"research","expected_revision":0,"plan":plan,"approved":True}
        result=app.dispatch("POST",route+"/tool-campaign-run",body)[1]
        assert result["status"]=="complete" and result["calls"]==3
        assert result["results"]["lookup"]["result"]["hit_count"]==1
        assert result["results"]["verify"]["result"]["identity_verified"]
        assert result["results"]["skip"]["status"]=="skipped"
        assert result["results"]["math"]["result"]["numerator"]=="33"
        assert result["results"]["math"]["result"]["denominator"]=="1"
        assert not result["knowledge_modified"] and not result["transcript_committed"]
        assert app.dispatch("GET",route)[1]==before
    finally:
        app.close()
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime()),path,token="t"*64)
    try:
        replay=app.dispatch("POST",route+"/tool-campaign-run",body)[1]
        assert replay["replayed"] is True and replay["results"]==result["results"]
        assert app.dispatch("GET",route)[1]==before
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/tool-campaign-run",body|{"plan":plan|{"maximum_calls":4}})
        assert exc.value.status==409
    finally:
        app.close()


def test_tool_campaign_refuses_unapproved_tools_and_uncertain_restart(tmp_path):
    path=tmp_path/"chat.sqlite3"
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime()),path,token="t"*64)
    try:
        sid,route=session(app)
        plan={"actions":[action("math","calculate",{"expression":"1+2"})],
              "maximum_calls":1,"maximum_seconds":10}
        body={"campaign_id":"lost","expected_revision":0,"plan":plan,"approved":True}
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/tool-campaign-run",body|{"approved":False})
        assert exc.value.status==403
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/tool-campaign-run",body|{"plan":plan|(
                {"actions":[action("shell","shell",{"command":"anything"})]})})
        assert exc.value.status==400
        row,created=app.competitive.tools.begin(sid,"lost",0,plan)
        assert created and row["status"]=="running"
    finally:
        app.close()
    app=OfflineHTTPApplication(NativeRuntimeLocalModel(runtime()),path,token="t"*64)
    try:
        result=app.dispatch("POST",route+"/tool-campaign-run",body)[1]
        assert result["replayed"] and result["status"]=="running" and result["calls"]==0
        abandoned=app.dispatch("POST",route+"/tool-campaign-abandon",
            {"campaign_id":"lost","plan_sha256":row["plan_sha256"],"approved":True})[1]
        assert abandoned["status"]=="abandoned_unconfirmed"
    finally:
        app.close()


def test_browser_competitive_controls_are_explicit():
    from skeleton.app.offline_web import HTML,JAVASCRIPT,CSS
    for element in ("competitive-panel","competitive-ensemble","competitive-speculative",
                    "competitive-media","competitive-prefetch","competitive-tool-run"):
        assert f'id="{element}"' in HTML
    assert "Inspect the same ID before any new execution" in JAVASCRIPT
    assert "get('competitive-media-file').value='';" in JAVASCRIPT
    assert "#competitive-panel[open]" in CSS
