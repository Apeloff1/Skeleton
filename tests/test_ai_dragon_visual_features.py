"""Visual decoder custody regressions."""
import sqlite3,pytest
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_frame_custody import bind_extracted_frames
from skeleton.ai.webcrawler.dragon_visual_features import VisualObservation,bind_visual_observations
from skeleton.ai.webcrawler.dragon_motion_features import derive_motion_features

def setup():
 db=sqlite3.connect(":memory:");q=DragonAnalysisQueue(db);l=DragonConsentLedger(db)
 c=l.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,policy_version="v1",scope_digest="a"*64,authorized=True)
 cq=ConsentBoundAnalysisQueue(q,l,db);j=cq.submit("u","b"*64,"g",consent_id=c.consent_id,scope_digest="a"*64,now=2,authorized=True)
 b=bind_extracted_frames(cq,"u",j.job_id,((0,"c"*64,"f0"),(16,"d"*64,"f1")),retention_until=90,authorized=True)
 obs=tuple(VisualObservation(f.frame_id,f.frame_digest,.2+i*.1,.3,.4+i*.2,.1) for i,f in enumerate(b.frames))
 return cq,j,b,obs

def test_visual_features_bind_exact_source_frames():
 cq,j,b,obs=setup();out=bind_visual_observations(cq,"u",j.job_id,b,obs,now=3,authorized=True)
 assert [x.source_frame_id for x in out.frames]==[x.frame_id for x in b.frames]
 assert out.source_batch_fingerprint==b.batch_fingerprint

def test_decoder_frame_substitution_fails_closed():
 cq,j,b,obs=setup();bad=(replace(obs[0],frame_digest="e"*64),obs[1])
 with pytest.raises(ValueError,match="does not bind"):
  bind_visual_observations(cq,"u",j.job_id,b,bad,now=3,authorized=True)

def test_malformed_decoder_output_fails_closed():
 cq,j,b,obs=setup();bad=(replace(obs[0],motion_energy=1.1),obs[1])
 with pytest.raises(ValueError,match="normalized"):
  bind_visual_observations(cq,"u",j.job_id,b,bad,now=3,authorized=True)

def test_motion_features_preserve_decoder_motion_and_source_identity():
 cq,j,b,obs=setup();visual=bind_visual_observations(cq,"u",j.job_id,b,obs,now=3,authorized=True)
 motion=derive_motion_features(visual,authorized=True)
 assert motion.frames[1].features[0]==.6
 assert motion.frames[1].source_frame_id==b.frames[1].frame_id
 assert motion.visual_fingerprint==visual.observation_fingerprint
