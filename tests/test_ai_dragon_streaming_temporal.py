"""Streaming temporal segmentation invariance regressions."""
import sqlite3
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_temporal_segmentation import FeatureFrame
from skeleton.ai.webcrawler.dragon_streaming_temporal import segment_streaming_with_consent

def setup():
 db=sqlite3.connect(":memory:");q=DragonAnalysisQueue(db);l=DragonConsentLedger(db)
 c=l.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,policy_version="v",scope_digest="a"*64,authorized=True)
 cq=ConsentBoundAnalysisQueue(q,l,db);j=cq.submit("u","b"*64,"g",consent_id=c.consent_id,scope_digest="a"*64,now=2,authorized=True)
 frames=tuple(FeatureFrame(i*100,(0.05 if i<8 else .8 if i<12 else .06,),str(i)) for i in range(20))
 return cq,j,frames

def test_event_boundaries_do_not_depend_on_checkpoint_size():
 cq,j,f=setup()
 a=segment_streaming_with_consent(cq,"u",j.job_id,f,now=3,authorized=True,checkpoint_frames=2)
 b=segment_streaming_with_consent(cq,"u",j.job_id,f,now=3,authorized=True,checkpoint_frames=7)
 assert a.events==b.events and a.trace_fingerprint==b.trace_fingerprint
 assert a.checkpoints!=b.checkpoints

def test_trace_fingerprint_changes_when_source_trace_changes():
 cq,j,f=setup();a=segment_streaming_with_consent(cq,"u",j.job_id,f,now=3,authorized=True,checkpoint_frames=3)
 changed=f[:-1]+(FeatureFrame(f[-1].timestamp_ms,(.5,),f[-1].source_frame_id),)
 b=segment_streaming_with_consent(cq,"u",j.job_id,changed,now=3,authorized=True,checkpoint_frames=3)
 assert a.trace_fingerprint!=b.trace_fingerprint


def test_consent_expiry_during_checkpoints_fails_closed():
 cq,j,f=setup();times=iter([3,4,101])
 with __import__("pytest").raises(PermissionError):
  segment_streaming_with_consent(cq,"u",j.job_id,f,clock=lambda:next(times),authorized=True,checkpoint_frames=2)

def test_checkpoint_clock_regression_fails_closed():
 cq,j,f=setup();times=iter([3,2])
 with __import__("pytest").raises(RuntimeError,match="clock regressed"):
  segment_streaming_with_consent(cq,"u",j.job_id,f,clock=lambda:next(times),authorized=True,checkpoint_frames=2)
