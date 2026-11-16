"""Actual native model decisions within an immutable, permission-closed tool graph."""
import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer
from skeleton.app.offline_http import OfflineHTTPApplication,OfflineHTTPError
from skeleton.app.jeeves_model_tool_selector import NativeToolSelector
from skeleton.app.jeeves_tool_campaign import normalize_plan,digest,ToolCampaignError


def app_for(path):
    runtime=NativeLLMRuntime(TinyTransformer(
        vocab=("system:","user:","assistant:","hello","world","answer","local","offline","jeeves",
               "alpha","beta","gamma","stop","."," "),dim=8,ctx=1024,seed=41,n_heads=2,n_layers=2,d_ff=16))
    return OfflineHTTPApplication(NativeRuntimeLocalModel(runtime),path,token="t"*64)


def action(name,expression,deps=()):
    return {"id":name,"kind":"calculate","arguments":{"expression":expression},
            "depends_on":list(deps),"condition":{"kind":"always","action":None}}


def plan():
    return {"actions":[action("one","2+3"),action("two","7*8"),action("three","9/3",["one"])],
            "maximum_calls":3,"maximum_seconds":40,
            "selector":{"goal":"Calculate useful results","labels":{"one":"alpha","two":"beta","three":"gamma"},
                        "stop_label":"stop","maximum_decisions":3}}


def test_actual_model_selector_receipt_binds_ready_actions_and_replays(tmp_path):
    path=tmp_path/"tools.sqlite3"
    app=app_for(path)
    try:
        sid=app.dispatch("POST","/v1/sessions",{})[1]["session_id"]
        route="/v1/sessions/"+sid
        before=app.dispatch("GET",route)[1]
        body={"campaign_id":"neural-actions","expected_revision":0,"plan":plan(),"approved":True}
        result=app.dispatch("POST",route+"/tool-campaign-run",body)[1]
        assert result["model_directed_selection"] is True
        assert result["selector_receipts"]
        assert not result["model_generated_tool_arguments"]
        assert result["calls"]<=3
        seen=set()
        for decision in result["selector_receipts"]:
            assert decision["model_graph_executed"] is True
            assert decision["model_digest"]==app.model_digest
            assert decision["tokenizer_digest"]==app.tokenizer_digest
            assert decision["receipt_sha256"]==digest({k:v for k,v in decision.items() if k!="receipt_sha256"})
            assert decision["authority_expanded"] is False
            assert not decision["new_arguments_generated"]
            if decision["selected_action"] is None:
                assert result["stop_reason"]=="model_selected_stop"
                break
            chosen=decision["selected_action"]
            assert chosen in decision["ready_actions"] and chosen not in seen
            if chosen=="three":
                assert "one" in seen
            assert result["results"][chosen]["status"]=="succeeded"
            seen.add(chosen)
        assert result["calls"]==len(seen)
        assert app.dispatch("GET",route)[1]==before
    finally:
        app.close()
    app=app_for(path)
    try:
        replay=app.dispatch("POST",route+"/tool-campaign-run",body)[1]
        assert replay["replayed"] is True
        assert replay["selector_receipts"]==result["selector_receipts"]
        assert replay["results"]==result["results"]
    finally:
        app.close()


def test_model_selector_cannot_invent_labels_or_expand_tools(tmp_path):
    app=app_for(tmp_path/"denial.sqlite3")
    try:
        sid=app.dispatch("POST","/v1/sessions",{})[1]["session_id"]
        route="/v1/sessions/"+sid
        original=plan()
        bad=original|{"selector":original["selector"]|{"labels":{"one":"alpha","two":"alpha","three":"gamma"}}}
        with pytest.raises(ToolCampaignError):
            normalize_plan(bad)
        bad=original|{"selector":original["selector"]|{"labels":{"one":"alpha","two":"beta","unexpected":"gamma"}}}
        with pytest.raises(ToolCampaignError):
            normalize_plan(bad)
        bad=original|{"selector":original["selector"]|{"stop_label":"unknownlabel"}}
        with pytest.raises(ToolCampaignError):
            NativeToolSelector(app.backend.runtime,normalize_plan(bad)["selector"])
        mutation=original|{"actions":[{"id":"one","kind":"shell","arguments":{"command":"x"},
            "depends_on":[],"condition":{"kind":"always","action":None}}]}
        with pytest.raises(ToolCampaignError):
            normalize_plan(mutation)
        with pytest.raises(OfflineHTTPError) as exc:
            app.dispatch("POST",route+"/tool-campaign-run",{"campaign_id":"unapproved",
              "expected_revision":0,"plan":original,"approved":False})
        assert exc.value.status==403
    finally:
        app.close()
