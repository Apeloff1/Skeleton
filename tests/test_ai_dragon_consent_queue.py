"""Durable consent integration regressions for Dragon analysis queue."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_analysis_queue import DragonAnalysisQueue
from skeleton.ai.webcrawler.dragon_consent_ledger import DragonConsentLedger


def setup():
    db=sqlite3.connect(":memory:")
    return DragonAnalysisQueue(db), DragonConsentLedger(db)


def issue(ledger, *, expires=100.0, scope="a"):
    return ledger.issue(
        "owner", capture=True, analysis=True, issued_at=10.0,
        expires_at=expires, policy_version="v1", scope_digest=scope*64,
        authorized=True,
    )


def test_active_scoped_consent_queues_job():
    queue,ledger=setup(); consent=issue(ledger)
    job=queue.submit_with_consent(
        "owner", recording_digest="b"*64, game_label="game", now=20.0,
        consent_id=consent.consent_id, consent_scope_digest="a"*64,
        consent_ledger=ledger, authorized=True,
    )
    assert job.recording_digest=="b"*64


def test_scope_mismatch_fails_closed():
    queue,ledger=setup(); consent=issue(ledger)
    with pytest.raises(PermissionError,match="scope"):
        queue.submit_with_consent(
            "owner",recording_digest="b"*64,game_label="game",now=20,
            consent_id=consent.consent_id,consent_scope_digest="c"*64,
            consent_ledger=ledger,authorized=True)


def test_expired_consent_fails_closed():
    queue,ledger=setup(); consent=issue(ledger,expires=15)
    with pytest.raises(PermissionError,match="not active"):
        queue.submit_with_consent(
            "owner",recording_digest="b"*64,game_label="game",now=20,
            consent_id=consent.consent_id,consent_scope_digest="a"*64,
            consent_ledger=ledger,authorized=True)


def test_revoked_consent_fails_closed():
    queue,ledger=setup(); consent=issue(ledger)
    ledger.revoke("owner",consent.consent_id,now=15,authorized=True)
    with pytest.raises(PermissionError,match="not active"):
        queue.submit_with_consent(
            "owner",recording_digest="b"*64,game_label="game",now=20,
            consent_id=consent.consent_id,consent_scope_digest="a"*64,
            consent_ledger=ledger,authorized=True)
