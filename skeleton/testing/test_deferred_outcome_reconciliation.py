from __future__ import annotations
import hashlib
import pytest

from skeleton.ai.runtime.deferred.contracts import Budget, canonical_json, sha256_json
from skeleton.ai.runtime.deferred.catalog import build_registry
from skeleton.ai.runtime.deferred.executor import DeferredExecutor
from skeleton.ai.runtime.deferred.journal import DeferredJournalConflict, SqliteDeferredExecutionJournal
from skeleton.ai.runtime.deferred.reconciliation import DeferredOutcomeReconciler, ProviderOutcomeEvidence


def _started(tmp_path):
    registry = build_registry()
    record = registry.get("VOL-160")
    record.transition("verified")
    record.transition("enabled")
    journal = SqliteDeferredExecutionJournal(tmp_path / "reconcile.sqlite3")
    executor = DeferredExecutor(registry, journal=journal)
    executor.register_handler("VOL-160", lambda payload: {"ok": True}, handler_identity=record.spec.handler)
    executor.set_budget("VOL-160", Budget(max_attempts=1, max_cost_units=4, max_latency_ms=20))
    payload = {"value": 1}
    invocation = executor.prepare("VOL-160", "provider-outcome", payload, cost_units=1, latency_ms=2)
    started, created = journal.record_started(
        operation_id=invocation.operation_id,
        fingerprint=invocation.fingerprint,
        invocation=invocation.as_dict(),
        handler_identity=record.spec.handler,
    )
    assert created
    return journal, invocation, record


def _evidence(invocation, record, *, outcome, digest, signature="a" * 64):
    return ProviderOutcomeEvidence(
        operation_id=invocation.operation_id,
        invocation_fingerprint=invocation.fingerprint,
        handler_identity=record.spec.handler,
        provider_identity="provider.example/v1",
        outcome=outcome,
        outcome_digest=digest,
        evidence_nonce="provider-event-123",
        signature=signature,
    )


def test_reconciles_success_without_redispatch(tmp_path):
    journal, invocation, record = _started(tmp_path)
    result = {"answer": 42}
    digest = hashlib.sha256(canonical_json(result).encode()).hexdigest()
    evidence = _evidence(invocation, record, outcome="succeeded", digest=digest)
    verified = []
    reconciler = DeferredOutcomeReconciler(
        journal,
        verify_signature=lambda provider, material, signature: verified.append((provider, material, signature)) or True,
    )
    receipt = reconciler.reconcile(evidence, result=result)
    terminal = journal.load(invocation.operation_id)
    assert terminal is not None and terminal.state == "succeeded"
    assert terminal.terminal["result"] == result
    assert terminal.terminal["reconciliation"]["evidence_digest"] == evidence.evidence_digest
    assert receipt.terminal_record_digest == terminal.record_digest
    assert verified and verified[0][0] == "provider.example/v1"

    restarted = DeferredExecutor(build_registry(), journal=SqliteDeferredExecutionJournal(tmp_path / "reconcile.sqlite3"))
    restarted_record = restarted.registry.get("VOL-160")
    restarted_record.transition("verified")
    restarted_record.transition("enabled")
    restarted.register_handler("VOL-160", lambda payload: pytest.fail("reconciled effect must never redispatch"), handler_identity=restarted_record.spec.handler)
    restarted.set_budget("VOL-160", Budget(max_attempts=1, max_cost_units=4, max_latency_ms=20))
    replay = restarted.execute(invocation, {"value": 1})
    assert replay.result == result


def test_reconciliation_rejects_bad_signature_and_leaves_started(tmp_path):
    journal, invocation, record = _started(tmp_path)
    result = {"answer": 42}
    digest = hashlib.sha256(canonical_json(result).encode()).hexdigest()
    evidence = _evidence(invocation, record, outcome="succeeded", digest=digest)
    reconciler = DeferredOutcomeReconciler(journal, verify_signature=lambda *_: False)
    with pytest.raises(PermissionError, match="signature rejected"):
        reconciler.reconcile(evidence, result=result)
    assert journal.load(invocation.operation_id).state == "started"


def test_reconciliation_rejects_identity_and_result_digest_drift(tmp_path):
    journal, invocation, record = _started(tmp_path)
    result = {"answer": 42}
    good = hashlib.sha256(canonical_json(result).encode()).hexdigest()
    evidence = _evidence(invocation, record, outcome="succeeded", digest=good)
    reconciler = DeferredOutcomeReconciler(journal, verify_signature=lambda *_: True)
    drifted = ProviderOutcomeEvidence(
        operation_id=evidence.operation_id,
        invocation_fingerprint="b" * 64,
        handler_identity=evidence.handler_identity,
        provider_identity=evidence.provider_identity,
        outcome=evidence.outcome,
        outcome_digest=evidence.outcome_digest,
        evidence_nonce=evidence.evidence_nonce,
        signature=evidence.signature,
    )
    with pytest.raises(DeferredJournalConflict, match="fingerprint mismatch"):
        reconciler.reconcile(drifted, result=result)
    with pytest.raises(DeferredJournalConflict, match="result digest mismatch"):
        reconciler.reconcile(evidence, result={"answer": 43})
    assert journal.load(invocation.operation_id).state == "started"


def test_reconciliation_is_terminal_and_cannot_rewrite_outcome(tmp_path):
    journal, invocation, record = _started(tmp_path)
    error_digest = sha256_json({"provider_error": "timeout-after-accept"})
    evidence = _evidence(invocation, record, outcome="failed", digest=error_digest)
    reconciler = DeferredOutcomeReconciler(journal, verify_signature=lambda *_: True)
    receipt = reconciler.reconcile(evidence, error_type="ProviderTimeout")
    assert receipt.outcome == "failed"
    terminal = journal.load(invocation.operation_id)
    assert terminal is not None and terminal.state == "failed"
    with pytest.raises(DeferredJournalConflict, match="unresolved started state"):
        reconciler.reconcile(evidence, error_type="ProviderTimeout")


def test_reconciliation_requires_existing_started_record(tmp_path):
    journal, invocation, record = _started(tmp_path)
    missing = ProviderOutcomeEvidence(
        operation_id="missing-operation",
        invocation_fingerprint=invocation.fingerprint,
        handler_identity=record.spec.handler,
        provider_identity="provider.example/v1",
        outcome="failed",
        outcome_digest="c" * 64,
        evidence_nonce="event-missing",
        signature="d" * 64,
    )
    reconciler = DeferredOutcomeReconciler(journal, verify_signature=lambda *_: True)
    with pytest.raises(DeferredJournalConflict, match="existing journal record"):
        reconciler.reconcile(missing, error_type="Unknown")
