from __future__ import annotations

import pytest

import skeleton.ai.runtime.training.evaluation_store as store_module
from skeleton.ai.runtime.training.evaluation import EvaluationLedger
from skeleton.ai.runtime.training.verifier import (
    MeasuredVerifierError,
    MeasuredVerifierRunner,
    canonical,
)
from skeleton.testing.test_measured_local_verifier import _evaluate, _sources


def _executed_cases(tmp_path):
    _, sources = _sources()
    ledger = EvaluationLedger(tmp_path / "measured.sqlite3")
    runner = MeasuredVerifierRunner(ledger)
    _evaluate(runner, sources)
    binding = runner.store._load("measured")[0]
    cases = [runner.store.case("measured", index) for index in range(2)]
    return runner, binding, cases


def _pending(runner, binding):
    epoch = runner.store.start("fault-injection", binding, "fault-worker", 1)
    return epoch


def _append(runner, epoch, index, case):
    # Replay actual runner-executed evidence only inside a private fault drill.
    # Ordinary callers have no publication capability (covered by the main suite).
    runner.store.record_case(
        "fault-injection", index, case, "fault-worker", epoch, _token=runner._writer_token
    )


def _pending_state(runner):
    return runner.store._db.execute(
        "SELECT state,completed_cases,receipt_json FROM measured_eval_run WHERE run_id='fault-injection'"
    ).fetchone()


@pytest.mark.parametrize("limit", ("case", "aggregate"))
def test_evidence_admission_failure_preserves_committed_case_prefix(tmp_path, monkeypatch, limit):
    runner, binding, cases = _executed_cases(tmp_path)
    epoch = _pending(runner, binding)
    if limit == "case":
        monkeypatch.setattr(store_module, "MAX_CASE_BYTES", len(canonical(cases[0]).encode("utf-8")) - 1)
        index = 0
    else:
        _append(runner, epoch, 0, cases[0])
        monkeypatch.setattr(store_module, "MAX_RUN_EVIDENCE_BYTES", len(canonical(cases).encode("utf-8")) - 1)
        index = 1
    with pytest.raises(MeasuredVerifierError, match="byte bound"):
        _append(runner, epoch, index, cases[index])
    assert _pending_state(runner) == ("pending", index, None)
    assert (
        runner.store._db.execute(
            "SELECT count(*) FROM measured_eval_case WHERE run_id='fault-injection'"
        ).fetchone()[0]
        == index
    )


@pytest.mark.parametrize("limit", ("case", "aggregate"))
def test_oversized_case_history_is_rejected_before_fetching_payloads(tmp_path, monkeypatch, limit):
    runner, _binding, cases = _executed_cases(tmp_path)
    if limit == "case":
        monkeypatch.setattr(store_module, "MAX_CASE_BYTES", len(canonical(cases[0]).encode("utf-8")) - 1)
    else:
        monkeypatch.setattr(store_module, "MAX_RUN_EVIDENCE_BYTES", len(canonical(cases).encode("utf-8")) - 1)
    statements = []
    runner.store._db.set_trace_callback(statements.append)
    with pytest.raises(MeasuredVerifierError, match="aggregate or per-case byte bound"):
        runner.receipt("measured")
    runner.store._db.set_trace_callback(None)
    assert not any(
        "select case_index,payload,case_digest from measured_eval_case" in " ".join(sql.lower().split())
        for sql in statements
    )


def test_exact_aggregate_evidence_boundary_remains_readable(tmp_path, monkeypatch):
    runner, binding, cases = _executed_cases(tmp_path)
    epoch = _pending(runner, binding)
    limit = len(canonical(cases).encode("utf-8"))
    monkeypatch.setattr(store_module, "MAX_RUN_EVIDENCE_BYTES", limit)
    _append(runner, epoch, 0, cases[0])
    _append(runner, epoch, 1, cases[1])
    assert runner.store.case("fault-injection", 1) == cases[1]
    receipt = runner.store.complete("fault-injection", "fault-worker", epoch, _token=runner._writer_token)
    assert receipt.metrics["sample_count"] == 4
    assert runner.receipt("fault-injection") is receipt


def test_lease_expiry_during_case_validation_cannot_publish_a_case(tmp_path, monkeypatch):
    runner, binding, cases = _executed_cases(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr(store_module.time, "time", lambda: clock[0])
    epoch = _pending(runner, binding)
    original = store_module.validate_case

    def validate_then_expire(*args, **kwargs):
        original(*args, **kwargs)
        clock[0] += 2

    monkeypatch.setattr(store_module, "validate_case", validate_then_expire)
    with pytest.raises(MeasuredVerifierError, match="expired before evidence commit"):
        _append(runner, epoch, 0, cases[0])
    assert _pending_state(runner) == ("pending", 0, None)
    assert (
        runner.store._db.execute(
            "SELECT count(*) FROM measured_eval_case WHERE run_id='fault-injection'"
        ).fetchone()[0]
        == 0
    )


def test_lease_expiry_during_completion_rolls_back_receipt_and_report(tmp_path, monkeypatch):
    runner, binding, cases = _executed_cases(tmp_path)
    clock = [1000.0]
    monkeypatch.setattr(store_module.time, "time", lambda: clock[0])
    epoch = _pending(runner, binding)
    for index, case in enumerate(cases):
        _append(runner, epoch, index, case)
    tables = ("eval_result", "verifier_report", "measured_eval_qualification")
    before = [runner.store._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables]
    original = store_module._receipt

    def derive_then_expire(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] += 2
        return result

    monkeypatch.setattr(store_module, "_receipt", derive_then_expire)
    with pytest.raises(MeasuredVerifierError, match="expired before evidence commit"):
        runner.store.complete("fault-injection", "fault-worker", epoch, _token=runner._writer_token)
    assert _pending_state(runner) == ("pending", 2, None)
    assert [
        runner.store._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables
    ] == before
