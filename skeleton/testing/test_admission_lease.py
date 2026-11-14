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


def test_replaced_valid_database_cannot_reset_existing_admission_budget(tmp_path):
    path = tmp_path / "admission.db"
    original = AdmissionLease(path)
    for i in range(MAX_PUSHES_LAST_MINUTE):
        assert original.acquire("lane", f"sha{i}", "actor")
    replacement = tmp_path / "replacement.db"
    fresh = AdmissionLease(replacement)
    assert fresh.count_recent() == 0
    replacement.replace(path)
    with pytest.raises(RuntimeError, match="identity changed"):
        original.acquire("lane", "another", "actor")


def test_relative_path_is_pinned_at_initialization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = AdmissionLease("admission.db")
    assert original.acquire("A", "head", "actor")
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert original.count_recent() == 1
    assert not (other / "admission.db").exists()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 10**400, 1e300, True, "now"])
def test_invalid_clock_fails_closed_without_overflow(tmp_path, bad):
    now = [1000.0]
    ledger = AdmissionLease(tmp_path / "admission.db", clock=lambda: now[0])
    now[0] = bad
    with pytest.raises(RuntimeError, match="invalid admission clock"):
        ledger.acquire("A", "sha", "actor")
    now[0] = 1001.0
    assert ledger.count_recent() == 0


def test_hardlinked_or_symlinked_ledger_path_is_refused(tmp_path):
    path = tmp_path / "admission.db"
    ledger = AdmissionLease(path)
    alias = tmp_path / "alias.db"
    try:
        alias.hardlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("host does not support hardlinks")
    with pytest.raises(RuntimeError, match="private regular file"):
        ledger.count_recent()
    alias.unlink()
    try:
        alias.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("host does not support symlinks")
    with pytest.raises(RuntimeError, match="private regular file"):
        AdmissionLease(alias)
