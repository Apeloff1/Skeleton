"""Durable reviewer ledger regression fixtures (no production credentials)."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.independent_reviewer_policy import PolicyDenied, ReviewerPolicySigner
from scripts.independent_reviewer_replay import DurableReplayLedger, initialize
from skeleton.testing.test_independent_reviewer_service import CLIENT, policy, review, challenge

OPTIONS = dict(ledger_id="b"*64, authority="reviewer", domain="separate-domain")
pytestmark = pytest.mark.skipif(os.name != "posix", reason="private POSIX storage")


def open_ledger(tmp_path, capacity=8):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "replay.sqlite3"
    initialize(path, capacity=capacity, **OPTIONS)
    return path, DurableReplayLedger(path, **OPTIONS)


def test_nonce_stays_consumed_across_reopen_and_policy_rotation(tmp_path):
    path, ledger = open_ledger(tmp_path)
    key = Ed25519PrivateKey.generate()
    first = ReviewerPolicySigner(policy(), key, replay_ledger=ledger)
    nonce = "1"*48
    first.review(review(nonce=nonce), CLIENT)
    other = ReviewerPolicySigner(policy(approved_contexts=[]), Ed25519PrivateKey.generate(),
                                  replay_ledger=DurableReplayLedger(path, **OPTIONS))
    with pytest.raises(PolicyDenied):
        other.attest(challenge(nonce=nonce), CLIENT)
    denied = other.review(review(nonce="2"*48), CLIENT)
    assert b'"allowed":false' in denied
    with pytest.raises(PolicyDenied):
        first.review(review(nonce="2"*48), CLIENT)


def test_concurrent_independent_connections_admit_only_one_nonce(tmp_path):
    path, _ = open_ledger(tmp_path)
    ledgers = [DurableReplayLedger(path, **OPTIONS) for _ in range(8)]
    def consume(ledger):
        try:
            ledger.consume("3"*48)
            return True
        except PolicyDenied:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, ledgers)) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT consumed FROM ledger_identity").fetchone() == (1,)
        rows = conn.execute("SELECT nonce_sha256 FROM consumed_nonces").fetchall()
        assert len(rows) == 1 and len(rows[0][0]) == 64
        assert "3"*48 not in rows[0][0]


def test_exhaustion_does_not_reset_even_after_reopen(tmp_path):
    path, ledger = open_ledger(tmp_path, capacity=2)
    ledger.consume("1"*48)
    ledger.consume("2"*48)
    with pytest.raises(PolicyDenied):
        DurableReplayLedger(path, **OPTIONS).consume("3"*48)
    with pytest.raises(FileExistsError):
        initialize(path, capacity=3, **OPTIONS)


def test_absent_wrong_identity_and_replaced_file_denied(tmp_path):
    path, ledger = open_ledger(tmp_path)
    with pytest.raises(PolicyDenied):
        DurableReplayLedger(path, **{**OPTIONS,"ledger_id":"a"*64})
    alias = path.with_name("alias.sqlite3")
    alias.symlink_to(path)
    with pytest.raises(PolicyDenied):
        DurableReplayLedger(alias, **OPTIONS)
    path.rename(path.with_name("old.sqlite3"))
    with pytest.raises(PolicyDenied):
        DurableReplayLedger(path, **OPTIONS)
    initialize(path, capacity=8, **OPTIONS)
    with pytest.raises(PolicyDenied):
        ledger.consume("1"*48)


def test_schema_and_count_tampering_denied_on_open(tmp_path):
    path, ledger = open_ledger(tmp_path)
    ledger.consume("1"*48)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM consumed_nonces")
    with pytest.raises(PolicyDenied):
        DurableReplayLedger(path, **OPTIONS)
