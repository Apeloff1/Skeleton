"""Local admission custody regressions; no remote writes or network."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from skeleton.admission.lease import AdmissionLease, MAX_PUSHES_LAST_MINUTE


def test_acquire_release_and_replay(tmp_path):
    ledger = AdmissionLease(tmp_path / "admission.db")
    token = ledger.acquire("A", "abc123", "bot")
    assert token is not None
    assert ledger.count_recent() == 1
    with pytest.raises(RuntimeError, match="SHA mismatch"):
        ledger.release(token, "wrong")
    with pytest.raises(RuntimeError, match="unknown"):
        ledger.release(replace(token, actor="other"), "abc123")
    ledger.release(token, "abc123")
    with pytest.raises(RuntimeError, match="consumed"):
        ledger.release(token, "abc123")
    assert ledger.count_recent() == 1


def test_unreleased_reservations_consume_headroom(tmp_path):
    ledger = AdmissionLease(tmp_path / "admission.db")
    for i in range(MAX_PUSHES_LAST_MINUTE):
        assert ledger.acquire("lane", f"sha{i}", "bot") is not None
    assert ledger.acquire("lane", "extra", "bot") is None
    assert ledger.count_recent() == MAX_PUSHES_LAST_MINUTE


@pytest.mark.parametrize("same_lane", [False, True])
def test_same_head_cannot_be_reserved_twice(tmp_path, same_lane):
    ledger = AdmissionLease(tmp_path / "admission.db")
    assert ledger.acquire("A", "same", "bot1")
    with pytest.raises(RuntimeError, match="concurrent mutation"):
        ledger.acquire("A" if same_lane else "B", "same", "bot2")


def test_simultaneous_connections_share_budget(tmp_path):
    path = tmp_path / "admission.db"
    ledger = AdmissionLease(path)
    barrier = Barrier(8)

    def contender(i):
        worker = AdmissionLease(path)
        barrier.wait(timeout=10)
        return worker.acquire(str(i), f"sha{i}", "bot")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(contender, range(8)))
    assert sum(token is not None for token in results) == MAX_PUSHES_LAST_MINUTE
    assert ledger.count_recent() == MAX_PUSHES_LAST_MINUTE


def test_expiry_clock_regression_and_restart(tmp_path):
    now = [1000.0]
    path = tmp_path / "admission.db"
    ledger = AdmissionLease(path, clock=lambda: now[0])
    token = ledger.acquire("A", "sha", "actor")
    assert token is not None
    now[0] += 59
    assert AdmissionLease(path, clock=lambda: now[0]).count_recent() == 1
    now[0] -= 1
    with pytest.raises(RuntimeError, match="clock regressed"):
        ledger.count_recent()
    now[0] = 1060
    with pytest.raises(RuntimeError, match="expired"):
        ledger.release(token, "sha")
    assert ledger.count_recent() == 0
    assert ledger.acquire("A", "sha", "actor")


def test_missing_or_corrupt_ledger_fails_closed(tmp_path):
    path = tmp_path / "admission.db"
    ledger = AdmissionLease(path)
    path.unlink()
    with pytest.raises(RuntimeError, match="unavailable"):
        ledger.count_recent()
    path.write_text('{"leases":[],"pushes":[]}')
    with pytest.raises(RuntimeError, match="unavailable"):
        AdmissionLease(path)
