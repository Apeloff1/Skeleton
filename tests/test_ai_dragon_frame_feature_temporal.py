"""Feature custody and chunked temporal regressions."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_frame_custody import bind_extracted_frames
from skeleton.ai.webcrawler.dragon_frame_features import extract_custodied_features
from skeleton.ai.webcrawler.dragon_chunked_temporal import segment_with_consent_checkpoints

def setup():
 db=sqlite3.connect(":memory:");q=DragonAnalysisQueue(db);l=DragonConsentLedger(db)
 c=l.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,policy_version="v1",scope_digest="a"*64,authorized=True)
 cq=ConsentBoundAnalysisQueue(q,l,db);j=cq.submit("u","b"*64,"g",consent_id=c.consent_id,scope_digest="a"*64,now=2,authorized=True)
 b=bind_extracted_frames(cq,"u",j.job_id,tuple((i*16,("%064x"%(i+1))[-64:],f"frame://{i}") for i in range(8)),retention_until=90,authorized=True)
 return l,cq,c,j,b

def test_features_preserve_source_frame_identity():
 _,cq,_,j,b=setup(); f=extract_custodied_features(cq,"u",j.job_id,b,now=3,authorized=True)
 assert tuple(x.source_frame_id for x in f.frames)==tuple(x.frame_id for x in b.frames)
 assert all(len(x.features)==3 for x in f.frames)

def test_expired_retention_blocks_features():
 _,cq,_,j,b=setup()
 with pytest.raises(PermissionError,match="retention"):
  extract_custodied_features(cq,"u",j.job_id,b,now=91,authorized=True)

def test_chunked_temporal_checks_consent_multiple_times():
 _,cq,_,j,b=setup(); f=extract_custodied_features(cq,"u",j.job_id,b,now=3,authorized=True)
 out=segment_with_consent_checkpoints(cq,"u",j.job_id,f.frames,now=3,authorized=True,chunk_size=2)
 assert out.chunks_checked>=4

def test_revocation_blocks_chunked_temporal():
 l,cq,c,j,b=setup(); f=extract_custodied_features(cq,"u",j.job_id,b,now=3,authorized=True)
 l.revoke("u",c.consent_id,revoked_at=4,authorized=True)
 with pytest.raises(PermissionError):
  segment_with_consent_checkpoints(cq,"u",j.job_id,f.frames,now=5,authorized=True,chunk_size=2)
