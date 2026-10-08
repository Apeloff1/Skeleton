"""Visual runtime transaction regressions."""
import sqlite3,pytest
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_analysis_runtime import DragonAnalysisRuntime
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_runtime_events import DragonRuntimeEventLedger
from skeleton.ai.webcrawler.dragon_frame_custody import CapturedFrame
from skeleton.ai.webcrawler.dragon_visual_features import VisualObservation
from skeleton.ai.webcrawler.dragon_browser_visual_import import BrowserVisualEnvelope,SCHEMA,canonical_browser_visual_fingerprint
from skeleton.ai.webcrawler.dragon_visual_runtime_ingest import ingest_browser_visual,_commit_stage

def setup():
 db=sqlite3.connect(":memory:");q=DragonAnalysisQueue(db);l=DragonConsentLedger(db)
 c=l.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,policy_version="v1",scope_digest="a"*64,authorized=True)
 cq=ConsentBoundAnalysisQueue(q,l,db);j=cq.submit("u","b"*64,"g",consent_id=c.consent_id,scope_digest="a"*64,now=2,authorized=True)
 fs=tuple(CapturedFrame(("%064x"%(i+1))[-64:],"x","x","x","x","x",i*500,("%064x"%(i+20))[-64:],90,f"local://{i}") for i in range(4))
 os=tuple(VisualObservation(f.frame_id,f.frame_digest,.2,.2,.1 if i<2 else .9,.1 if i<2 else .9) for i,f in enumerate(fs))
 e=BrowserVisualEnvelope(SCHEMA,"u",j.job_id,"b"*64,c.consent_id,"a"*64,90,fs,os,"")
 e=replace(e,payload_fingerprint=canonical_browser_visual_fingerprint(e))
 rt=DragonAnalysisRuntime(db);rt.create("u","run",now=2,authorized=True)
 return l,cq,c,j,e,rt

def test_ingest_commits_source_then_temporal():
 _,cq,_,_,e,rt=setup();out=ingest_browser_visual(rt,cq,e,"run",now=3,authorized=True,chunk_size=2)
 assert out.checkpoint.revision==2
 cp=rt.checkpoint("u","run",authorized=True)
 assert cp.revision==2

def test_cancelled_runtime_rejects_ingest():
 _,cq,_,_,e,rt=setup();rt.cancel("u","run",now=3,authorized=True)
 with pytest.raises(PermissionError,match="not active"):ingest_browser_visual(rt,cq,e,"run",now=4,authorized=True)

def test_revoked_consent_rejects_before_runtime_receipt():
 l,cq,c,_,e,rt=setup();l.revoke("u",c.consent_id,revoked_at=3,authorized=True)
 with pytest.raises(PermissionError):ingest_browser_visual(rt,cq,e,"run",now=4,authorized=True)
 assert rt.checkpoint("u","run",authorized=True).revision==0

def test_mutated_envelope_cannot_advance_runtime():
 _,cq,_,_,e,rt=setup();bad=replace(e,recording_digest="e"*64)
 with pytest.raises(ValueError):ingest_browser_visual(rt,cq,bad,"run",now=3,authorized=True)
 assert rt.checkpoint("u","run",authorized=True).revision==0


def test_stage_receipt_rolls_back_when_forensic_event_cannot_append():
 _,_,_,_,_,rt=setup()
 ledger=DragonRuntimeEventLedger(rt.db)
 ledger.append("u","run",event_type="sentinel",layer="source_integrity",outcome="accepted",
  evidence_fingerprint="b"*64,occurred_at=5,authorized=True)
 receipt=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"a"*64,1,True)
 with pytest.raises(ValueError,match="time regression"):
  _commit_stage(rt,ledger,"u","run",receipt,now=3,expected_revision=0)
 assert rt.checkpoint("u","run",authorized=True).revision==0
 events=ledger.events("u","run",authorized=True)
 assert len(events)==1 and events[0].event_type=="sentinel"
