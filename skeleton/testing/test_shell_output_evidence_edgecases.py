"""Output, cache, history, replay, and retention edge cases."""

from __future__ import annotations

import pytest

from skeleton.shells.attestations import HMACAttestor
from skeleton.shells.execution_cache import ExecutionCache
from skeleton.shells.execution_history import ExecutionHistory, HistoryQuery
from skeleton.shells.output_policy import OutputClass, OutputClassifier, OutputRetention, OutputRetentionPolicy
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.replay import EvidenceReplay, ReplayStatus
from skeleton.shells.retention import OutputRetentionStore
from skeleton.shells.runner import ShellResult


def result(stdout=b"", stderr=b"", ok=True):
    return ShellResult("python", 0 if ok else 1, stdout, stderr, False, False, ok)


def receipt(command="python", correlation="c", attempt=1):
    return ExecutionReceipt(
        command=command,
        correlation_id=correlation,
        fingerprint="fp",
        started_at="s",
        finished_at="f",
        duration_ms=0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=0,
        stderr_bytes=0,
        attempt=attempt,
    )


def test_classifier_non_utf8_does_not_raise():
    classifier = OutputClassifier(secret_patterns=("secret",))
    assert classifier.classify(b"\xff\xfe") is OutputClass.INTERNAL


def test_classifier_case_insensitive():
    classifier = OutputClassifier(secret_patterns=("token=",))
    assert classifier.classify(b"ToKeN=value") is OutputClass.SECRET


def test_custom_public_rule_truncates():
    rules = {
        cls: OutputRetention(cls, True, True, 2, 1)
        for cls in OutputClass
    }
    output = OutputRetentionPolicy(rules).apply(b"abcd", OutputClass.PUBLIC)
    assert output.retained == b"ab"
    assert output.truncated


def test_retention_zero_seconds_expires_immediately():
    now = [0.0]
    policy = OutputRetentionPolicy()
    output = policy.apply(b"x", OutputClass.INTERNAL)
    store = OutputRetentionStore(clock=lambda: now[0])
    store.put("x", output, retention_seconds=0)
    assert store.get("x") is None


def test_retention_snapshot_sorted():
    policy = OutputRetentionPolicy()
    output = policy.apply(b"x", OutputClass.INTERNAL)
    store = OutputRetentionStore()
    store.put("b", output, retention_seconds=10)
    store.put("a", output, retention_seconds=10)
    assert [item.key for item in store.snapshot()] == ["a", "b"]


def test_cache_snapshot_sorted():
    cache = ExecutionCache()
    cache.put("b", result())
    cache.put("a", result())
    assert [item.fingerprint for item in cache.snapshot()] == ["a", "b"]


def test_cache_hit_count_increments_each_get():
    cache = ExecutionCache()
    cache.put("x", result())
    assert cache.get("x").hits == 1
    assert cache.get("x").hits == 2


def test_cache_clear():
    cache = ExecutionCache()
    cache.put("x", result())
    cache.clear()
    assert cache.snapshot() == ()


def test_history_query_correlation():
    history = ExecutionHistory()
    a = receipt(correlation="a")
    b = receipt(correlation="b")
    history.extend((a, b))
    assert history.query(HistoryQuery(correlation_id="a")) == (a,)


def test_history_query_attempt_independent():
    history = ExecutionHistory()
    a = receipt(attempt=1)
    b = receipt(correlation="b", attempt=2)
    history.extend((a, b))
    assert len(history.snapshot()) == 2


def test_replay_mixed_attestation_statuses():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    a = receipt(correlation="a")
    b = receipt(correlation="b")
    attestations = {a.receipt_id: attestor.sign_receipt(a)}
    report = EvidenceReplay().verify_attested((a, b), attestations, attestor)
    statuses = [item.status for item in report.items]
    assert statuses == [ReplayStatus.VERIFIED, ReplayStatus.MISSING_ATTESTATION]
    assert not report.valid
