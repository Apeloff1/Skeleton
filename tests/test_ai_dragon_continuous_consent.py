"""Continuous consent-custody regressions."""
import sqlite3, pytest
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue,JobStatus
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger
from skeleton.ai.webcrawler.dragon_consent_bound_queue import ConsentBoundAnalysisQueue


def system():
    db=sqlite3.connect(":memory:")
    ledger=DragonConsentLedger(db)
    queue=ConsentBoundAnalysisQueue(DragonAnalysisQueue(db),ledger)
    consent=ledger.issue("u",capture=True,analysis=True,issued_at=1,
        expires_at=100,policy_version="v1",scope_digest="a"*64,
        authorized=True)
    return queue,ledger,consent


def test_job_persists_consent_binding():
    q,_,c=system(); job=q.submit("u",recording_digest="b"*64,
        game_label="g",now=2,consent_id=c.consent_id,
        scope_digest="a"*64,authorized=True)
    assert q.binding("u",job.job_id,authorized=True).consent_id==c.consent_id


def test_revocation_blocks_running_transition():
    q,l,c=system(); job=q.submit("u",recording_digest="b"*64,
        game_label="g",now=2,consent_id=c.consent_id,
        scope_digest="a"*64,authorized=True)
    l.revoke("u",c.consent_id,now=3,authorized=True)
    with pytest.raises(PermissionError):
        q.advance("u",job.job_id,JobStatus.RUNNING,now=4,authorized=True)


def test_revocation_sweep_cancels_pending_job():
    q,l,c=system(); job=q.submit("u",recording_digest="b"*64,
        game_label="g",now=2,consent_id=c.consent_id,
        scope_digest="a"*64,authorized=True)
    l.revoke("u",c.consent_id,now=3,authorized=True)
    assert q.cancel_revoked("u",now=4,authorized=True)==(job.job_id,)
    assert q.queue.get("u",job.job_id,authorized=True).status is JobStatus.CANCELLED


def test_binding_is_immutable():
    q,l,c=system(); job=q.submit("u",recording_digest="b"*64,
        game_label="g",now=2,consent_id=c.consent_id,
        scope_digest="a"*64,authorized=True)
    c2=l.issue("u",capture=True,analysis=True,issued_at=3,expires_at=100,
        policy_version="v2",scope_digest="c"*64,authorized=True)
    with pytest.raises(ValueError,match="immutable"):
        q.submit("u",recording_digest="b"*64,game_label="g",now=4,
            consent_id=c2.consent_id,scope_digest="c"*64,authorized=True)
