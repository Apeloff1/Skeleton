from __future__ import annotations
from dataclasses import replace
import hashlib
import pytest
from skeleton.ai.functional_transaction import *

SHA=hashlib.sha256(b"x").hexdigest()
def request():
 return VS001Request("REQUEST.1","CONVERSATION.1"," complete objective ",SHA,SHA)
def execution(*,tool=False,allowed=True,verified=True):
 r=request();intent=SHA if tool else None
 inf=InferenceOutcome("PROVIDER.LOCAL",r.digest,SHA,intent)
 auth=ToolAuthorization("AUTH.1",r.digest,SHA,"AUTHORITY.OPERATOR",allowed) if tool else None
 result=SHA if tool and allowed else None
 return VS001Execution("EXECUTION.1",r,inf,auth,result,verified)

def test_request_identity_normalizes_objective():
 r=request();assert r.objective=="complete objective"

def test_inference_must_bind_exact_request():
 r=request();bad=InferenceOutcome("PROVIDER.LOCAL","0"*64,SHA,None)
 with pytest.raises(FunctionalAIError,match="mismatch"):VS001Execution("EXECUTION.1",r,bad,None,None)

def test_tool_side_effect_requires_explicit_authority_and_result():
 r=request();inf=InferenceOutcome("PROVIDER.LOCAL",r.digest,SHA,SHA)
 with pytest.raises(FunctionalAIError,match="explicit authorization"):VS001Execution("EXECUTION.1",r,inf,None,None)
 denied=ToolAuthorization("AUTH.1",r.digest,SHA,"AUTHORITY.OPERATOR",False)
 with pytest.raises(FunctionalAIError,match="denied tool"):VS001Execution("EXECUTION.1",r,inf,denied,SHA)
 allowed=ToolAuthorization("AUTH.1",r.digest,SHA,"AUTHORITY.OPERATOR",True)
 with pytest.raises(FunctionalAIError,match="verified result"):VS001Execution("EXECUTION.1",r,inf,allowed,None)

def test_authorization_allowed_is_strict_boolean():
 r=request()
 with pytest.raises(FunctionalAIError,match="allowed must be bool"):ToolAuthorization("AUTH.1",r.digest,SHA,"AUTHORITY.OPERATOR",1)

def test_unverified_execution_cannot_commit():
 j=FunctionalAIJournal()
 with pytest.raises(FunctionalAIError,match="unverified execution"):j.commit(execution(verified=False),{"status":"done"},({"type":"terminal"},))

def test_commit_and_reconnect_replay_authoritative_frames():
 j=FunctionalAIJournal();x=execution();frames=({"seq":1,"text":"hello"},{"seq":2,"terminal":True})
 e=j.commit(x,{"status":"done"},frames)
 assert e.frame_count==2
 assert j.replay(x.request.request_id)==e
 assert j.replay_frames(x.request.request_id)==frames

def test_replay_returns_snapshot_not_mutable_authority():
 j=FunctionalAIJournal();x=execution();frames=({"seq":1,"nested":{"v":1}},)
 j.commit(x,{"status":"done"},frames)
 replay=j.replay_frames(x.request.request_id);replay[0]["nested"]["v"]=2
 assert j.replay_frames(x.request.request_id)[0]["nested"]["v"]==1

def test_terminal_outcome_is_immutable():
 j=FunctionalAIJournal();x=execution();j.commit(x,{"status":"done"},({"seq":1},))
 with pytest.raises(FunctionalAIError,match="immutable"):j.commit(x,{"status":"changed"},({"seq":1},))

def test_stream_must_be_nonempty_typed_and_bounded():
 j=FunctionalAIJournal();x=execution()
 with pytest.raises(FunctionalAIError,match="non-empty typed tuple"):j.commit(x,{},())
 with pytest.raises(FunctionalAIError,match="non-empty typed tuple"):j.commit(x,{},[{"seq":1}])

def test_replay_detects_authoritative_stream_corruption():
 j=FunctionalAIJournal();x=execution();j.commit(x,{},({"seq":1},))
 j._frames[x.request.request_id]=({"seq":2},)
 with pytest.raises(FunctionalAIError,match="diverged"):j.replay_frames(x.request.request_id)
