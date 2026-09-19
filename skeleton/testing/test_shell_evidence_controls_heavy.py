"""Evidence, event, attestation, replay, cache, trace, and failure-ledger tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.attestations import Attestation, AttestationError, HMACAttestor
from skeleton.shells.execution_cache import ExecutionCache
from skeleton.shells.execution_history import ExecutionHistory, HistoryQuery
from skeleton.shells.failure_ledger import ShellFailureKind, ShellFailureLedger
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.replay import EvidenceReplay, ReplayStatus
from skeleton.shells.runner import ShellResult
from skeleton.shells.shell_events import ShellEvents
from skeleton.shells.tracing import ShellTracer


def receipt(
    command="python",
    *,
    ok=True,
    correlation="c",
    attempt=1,
    timed_out=False,
    output_limited=False,
):
    return ExecutionReceipt(
        command=command,
        correlation_id=correlation,
        fingerprint="fp",
        started_at="s",
        finished_at="f",
        duration_ms=1,
        returncode=0 if ok else 1,
        ok=ok,
        timed_out=timed_out,
        output_limited=output_limited,
        stdout_bytes=1,
        stderr_bytes=2,
        attempt=attempt,
    )


def result(
    command="python",
    *,
    returncode=0,
    stdout=b"out",
    stderr=b"",
    timed_out=False,
    output_limited=False,
    accepted=True,
):
    return ShellResult(
        command,
        returncode,
        stdout,
        stderr,
        timed_out,
        output_limited,
        accepted,
    )


def test_events_emit_query_tail():
    events = ShellEvents()
    a = events.emit("start", correlation_id="c1", command="python")
    b = events.emit("end", correlation_id="c1", command="python")
    assert events.query(kind="start") == (a,)
    assert events.query(correlation_id="c1") == (a, b)
    assert events.tail(1) == (b,)


def test_events_observer_failure_isolated():
    events = ShellEvents()
    seen = []
    events.subscribe(lambda event: seen.append(event.kind))
    events.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    events.emit("x")
    assert seen == ["x"]


def test_events_unsubscribe():
    events = ShellEvents()
    sink = lambda event: None
    events.subscribe(sink)
    assert events.unsubscribe(sink)
    assert not events.unsubscribe(sink)


def test_events_ring_buffer():
    events = ShellEvents(max_events=2)
    events.emit("a")
    events.emit("b")
    events.emit("c")
    assert [event.kind for event in events.tail(10)] == ["b", "c"]


def test_attestor_requires_sufficient_key():
    with pytest.raises(AttestationError):
        HMACAttestor("k", b"short")


def test_attestor_sign_and_verify_payload():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    payload = {"a": 1, "b": 2}
    attestation = attestor.sign_payload(payload)
    assert attestor.verify_payload(payload, attestation)


def test_attestor_payload_order_is_canonical():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    a = attestor.sign_payload({"a": 1, "b": 2})
    b = attestor.sign_payload({"b": 2, "a": 1})
    assert a == b


def test_attestor_detects_payload_tamper():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    attestation = attestor.sign_payload({"a": 1})
    assert not attestor.verify_payload({"a": 2}, attestation)


def test_attestor_detects_signature_tamper():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    attestation = attestor.sign_payload({"a": 1})
    bad = replace(attestation, signature="0" * 64)
    assert not attestor.verify_payload({"a": 1}, bad)


def test_attestor_wrong_key_id_fails():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    attestation = attestor.sign_payload({"a": 1})
    bad = replace(attestation, key_id="other")
    assert not attestor.verify_payload({"a": 1}, bad)


def test_attestor_receipt_roundtrip():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    item = receipt()
    attestation = attestor.sign_receipt(item)
    assert attestor.verify_receipt(item, attestation)


def test_replay_chain_valid():
    chain = ReceiptChain()
    chain.append(receipt())
    chain.append(receipt(correlation="d"))
    report = EvidenceReplay().verify_chain(chain)
    assert report.valid
    assert all(item.status is ReplayStatus.VERIFIED for item in report.items)


def test_replay_chain_tamper_detected():
    chain = ReceiptChain()
    chain.append(receipt())
    item = chain._items[0]
    chain._items[0] = replace(item, receipt_hash="0" * 64)
    report = EvidenceReplay().verify_chain(chain)
    assert not report.valid
    assert report.items[0].status is ReplayStatus.INVALID_CHAIN


def test_replay_attested_valid():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    item = receipt()
    attestation = attestor.sign_receipt(item)
    report = EvidenceReplay().verify_attested(
        [item],
        {item.receipt_id: attestation},
        attestor,
    )
    assert report.valid


def test_replay_missing_attestation():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    item = receipt()
    report = EvidenceReplay().verify_attested([item], {}, attestor)
    assert not report.valid
    assert report.items[0].status is ReplayStatus.MISSING_ATTESTATION


def test_replay_invalid_attestation():
    attestor = HMACAttestor("k", b"0123456789abcdef")
    item = receipt()
    bad = Attestation("k", "hmac-sha256", "0" * 64, "0" * 64)
    report = EvidenceReplay().verify_attested([item], {item.receipt_id: bad}, attestor)
    assert report.items[0].status is ReplayStatus.INVALID_ATTESTATION


def test_execution_cache_put_get():
    now = [0.0]
    cache = ExecutionCache(clock=lambda: now[0])
    cached = cache.put("fp", result(), ttl_seconds=10)
    assert cached.hits == 0
    fetched = cache.get("fp")
    assert fetched.hits == 1
    assert fetched.stdout_digest
    assert fetched.stderr_digest


def test_execution_cache_does_not_store_output_bytes():
    cache = ExecutionCache()
    cached = cache.put("fp", result(stdout=b"secret"))
    assert not hasattr(cached, "stdout")
    assert cached.stdout_bytes == 6


def test_execution_cache_expiry():
    now = [0.0]
    cache = ExecutionCache(clock=lambda: now[0])
    cache.put("fp", result(), ttl_seconds=5)
    now[0] = 5
    assert cache.get("fp") is None


def test_execution_cache_evicts_oldest():
    now = [0.0]
    cache = ExecutionCache(max_entries=1, clock=lambda: now[0])
    cache.put("a", result(), ttl_seconds=10)
    now[0] = 1
    cache.put("b", result(), ttl_seconds=10)
    assert cache.get("a") is None
    assert cache.get("b") is not None


def test_execution_cache_invalidate():
    cache = ExecutionCache()
    cache.put("fp", result())
    assert cache.invalidate("fp")
    assert not cache.invalidate("fp")


def test_tracer_start_finish():
    now = [0.0]
    tracer = ShellTracer(clock=lambda: now[0])
    span = tracer.start("dispatch", trace_id="t")
    now[0] = 2
    finished = tracer.finish(span)
    assert finished.finished
    assert finished.duration_seconds == 2


def test_tracer_parent_child_shape():
    tracer = ShellTracer()
    parent = tracer.start("plan", trace_id="t")
    child = tracer.start("step", trace_id="t", parent_span_id=parent.span_id)
    assert child.parent_span_id == parent.span_id


def test_tracer_stale_finish_rejected():
    tracer = ShellTracer()
    span = tracer.start("x", trace_id="t")
    tracer.finish(span)
    with pytest.raises(RuntimeError):
        tracer.finish(span)


def test_tracer_eviction():
    tracer = ShellTracer(max_spans=1)
    first = tracer.start("a", trace_id="t")
    second = tracer.start("b", trace_id="t")
    assert first not in tracer.snapshot()
    assert second in tracer.snapshot()


def test_failure_ledger_record_query_count():
    ledger = ShellFailureLedger()
    a = ledger.record("python", ShellFailureKind.TIMEOUT, correlation_id="c", retryable=True)
    ledger.record("git", ShellFailureKind.INTERNAL)
    assert ledger.query(command="python") == (a,)
    assert ledger.query(kind=ShellFailureKind.TIMEOUT) == (a,)
    assert ledger.query(retryable=True) == (a,)
    assert ledger.counts()["timeout"] == 1
    assert ledger.counts()["internal"] == 1


def test_failure_ledger_ring_buffer():
    ledger = ShellFailureLedger(max_records=2)
    ledger.record("a", ShellFailureKind.INTERNAL)
    ledger.record("b", ShellFailureKind.INTERNAL)
    ledger.record("c", ShellFailureKind.INTERNAL)
    assert [item.command for item in ledger.tail(10)] == ["b", "c"]


def test_execution_history_append_query():
    history = ExecutionHistory()
    a = receipt(command="python", ok=True)
    b = receipt(command="git", ok=False, timed_out=True)
    history.append(a)
    history.append(b)
    assert history.query(HistoryQuery(command="python")) == (a,)
    assert history.query(HistoryQuery(ok=False)) == (b,)
    assert history.query(HistoryQuery(timed_out=True)) == (b,)


def test_execution_history_duplicate_rejected():
    history = ExecutionHistory()
    item = receipt()
    history.append(item)
    with pytest.raises(ValueError):
        history.append(item)


def test_execution_history_bounded():
    history = ExecutionHistory(max_receipts=1)
    a = receipt(correlation="a")
    b = receipt(correlation="b")
    history.append(a)
    history.append(b)
    assert history.snapshot() == (b,)


def test_execution_history_summary():
    history = ExecutionHistory()
    history.append(receipt(command="python", ok=True))
    history.append(receipt(command="python", ok=False, timed_out=True))
    history.append(receipt(command="git", ok=False, output_limited=True))
    summary = history.summary()
    assert summary.total == 3
    assert summary.succeeded == 1
    assert summary.failed == 2
    assert summary.timed_out == 1
    assert summary.output_limited == 1
    assert summary.commands == {"git": 1, "python": 2}
