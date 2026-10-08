"""Custodied temporal-worker regressions."""
import sqlite3, pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import AnalysisLayer,LayerReceipt
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from skeleton.ai.webcrawler.dragon_custodied_temporal_worker import execute_consent_bound_temporal
from skeleton.ai.webcrawler.dragon_temporal_segmentation import FeatureFrame


def setup():
    db=sqlite3.connect(":memory:"); ledger=DragonConsentLedger(db)
    q=ConsentBoundAnalysisQueue(DragonAnalysisQueue(db),ledger)
    c=ledger.issue("u",capture=True,analysis=True,issued_at=1,expires_at=100,
        policy_version="v1",scope_digest="a"*64,authorized=True)
    j=q.submit("u",recording_digest="b"*64,game_label="g",now=2,
        consent_id=c.consent_id,scope_digest="a"*64,authorized=True)
    root=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),"c"*64,2,True,False)
    dispatch=LayerDispatch(AnalysisLayer.TEMPORAL_SEGMENTATION,
        ("c"*64,),"temporal","v1")
    frames=(FeatureFrame(0,"f0",(0.,)),FeatureFrame(100,"f1",(1.,)))
    return q,ledger,c,j,root,dispatch,frames


def test_output_binds_recording_and_consent():
    q,_,c,j,root,d,frames=setup()
    result=execute_consent_bound_temporal(q,"u",j.job_id,d,frames,now=3,
        source_integrity_receipt=root,authorized=True)
    assert result.recording_digest=="b"*64
    assert result.consent_id==c.consent_id
    assert len(result.custody_fingerprint)==64


def test_revoked_consent_blocks_temporal_execution():
    q,l,c,j,root,d,frames=setup()
    l.revoke("u",c.consent_id,now=3,authorized=True)
    with pytest.raises(PermissionError):
        execute_consent_bound_temporal(q,"u",j.job_id,d,frames,now=4,
            source_integrity_receipt=root,authorized=True)


def test_unbound_legacy_job_cannot_use_strict_worker():
    q,_,_,_,root,d,frames=setup()
    legacy=q.queue.submit("u",recording_digest="d"*64,game_label="legacy",
        now=2,capture_consent=True,analysis_consent=True,authorized=True)
    with pytest.raises(PermissionError,match="no durable consent"):
        execute_consent_bound_temporal(q,"u",legacy.job_id,d,frames,now=3,
            source_integrity_receipt=root,authorized=True)
