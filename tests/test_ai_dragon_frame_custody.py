"""Frame-custody regressions."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_frame_custody import bind_extracted_frames

def setup():
    db=sqlite3.connect(":memory:"); q=DragonAnalysisQueue(db); l=DragonConsentLedger(db)
    c=l.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,
      policy_version="v1",scope_digest="a"*64,authorized=True)
    cq=ConsentBoundAnalysisQueue(q,l,db)
    j=cq.submit("u","b"*64,"game",consent_id=c.consent_id,
      scope_digest="a"*64,now=2,authorized=True)
    return l,cq,c,j

def test_frames_bind_recording_consent_scope_and_retention():
    _,cq,c,j=setup(); b=bind_extracted_frames(cq,"u",j.job_id,
      ((0,"c"*64,"frame://0"),(16,"d"*64,"frame://1")),
      retention_until=90,authorized=True)
    f=b.frames[0]
    assert f.recording_digest=="b"*64 and f.consent_id==c.consent_id
    assert f.consent_scope_digest=="a"*64 and f.retention_until==90

def test_revocation_blocks_frame_binding():
    l,cq,c,j=setup(); l.revoke("u",c.consent_id,revoked_at=3,authorized=True)
    with pytest.raises(PermissionError):
        bind_extracted_frames(cq,"u",j.job_id,((0,"c"*64,"frame://0"),),
          retention_until=90,authorized=True)

def test_non_monotonic_capture_fails_closed():
    _,cq,_,j=setup()
    with pytest.raises(ValueError,match="monotonic"):
        bind_extracted_frames(cq,"u",j.job_id,
          ((16,"c"*64,"frame://1"),(0,"d"*64,"frame://0")),
          retention_until=90,authorized=True)

def test_frame_identity_is_deterministic():
    _,cq,_,j=setup(); rows=((0,"c"*64,"frame://0"),)
    a=bind_extracted_frames(cq,"u",j.job_id,rows,retention_until=90,authorized=True)
    b=bind_extracted_frames(cq,"u",j.job_id,rows,retention_until=90,authorized=True)
    assert a.batch_fingerprint==b.batch_fingerprint
