"""Browser visual envelope boundary regressions."""
import sqlite3,pytest
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_frame_custody import CapturedFrame
from skeleton.ai.webcrawler.dragon_visual_features import VisualObservation
from skeleton.ai.webcrawler.dragon_browser_visual_import import BrowserVisualEnvelope,SCHEMA,canonical_browser_visual_fingerprint,accept_browser_visual

def setup():
 db=sqlite3.connect(":memory:");q=DragonAnalysisQueue(db);l=DragonConsentLedger(db)
 c=l.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,policy_version="v1",scope_digest="a"*64,authorized=True)
 cq=ConsentBoundAnalysisQueue(q,l);j=cq.submit("u",recording_digest="b"*64,game_label="g",consent_id=c.consent_id,scope_digest="a"*64,now=2,authorized=True)
 f=CapturedFrame("c"*64,"ignored","ignored","ignored","ignored","ignored",0,"d"*64,90,"local-frame://0")
 o=VisualObservation("c"*64,"d"*64,.2,.3,.4,.1)
 e=BrowserVisualEnvelope(SCHEMA,"u",j.job_id,"b"*64,c.consent_id,"a"*64,90,(f,),(o,),"")
 return cq,j,replace(e,payload_fingerprint=canonical_browser_visual_fingerprint(e))

def test_exact_envelope_imports_and_rebinds_server_custody():
 cq,j,e=setup();a=accept_browser_visual(cq,e,now=3,authorized=True)
 assert a.features.frames[0].source_frame_id!="c"*64
 assert len(a.features.frames[0].source_frame_id)==64

def test_mutated_observation_breaks_envelope_fingerprint():
 cq,_,e=setup();bad=replace(e,observations=(replace(e.observations[0],motion_energy=.9),))
 with pytest.raises(ValueError,match="fingerprint mismatch"):accept_browser_visual(cq,bad,now=3,authorized=True)

def test_recording_substitution_fails_before_analysis():
 cq,_,e=setup();bad=replace(e,recording_digest="e"*64)
 with pytest.raises(ValueError,match="recording substitution"):accept_browser_visual(cq,bad,now=3,authorized=True)

def test_retention_expiry_fails_closed():
 cq,_,e=setup()
 with pytest.raises(PermissionError,match="retention expired"):accept_browser_visual(cq,e,now=91,authorized=True)


def test_browser_controlled_frame_id_cannot_cross_custody_boundary():
 cq,_,e=setup();wire_id="f"*64
 frame=replace(e.frames[0],frame_id=wire_id)
 obs=replace(e.observations[0],frame_id=wire_id)
 unsigned=replace(e,frames=(frame,),observations=(obs,),payload_fingerprint="")
 changed=replace(unsigned,payload_fingerprint=canonical_browser_visual_fingerprint(unsigned))
 accepted=accept_browser_visual(cq,changed,now=3,authorized=True)
 assert accepted.features.frames[0].source_frame_id not in (wire_id,"c"*64)

def test_unknown_observation_transport_id_is_rejected_even_with_valid_envelope_hash():
 cq,_,e=setup();obs=replace(e.observations[0],frame_id="f"*64)
 unsigned=replace(e,observations=(obs,),payload_fingerprint="")
 changed=replace(unsigned,payload_fingerprint=canonical_browser_visual_fingerprint(unsigned))
 with pytest.raises(ValueError,match="unknown browser frame"):
  accept_browser_visual(cq,changed,now=3,authorized=True)
