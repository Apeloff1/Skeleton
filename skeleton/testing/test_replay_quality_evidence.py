"""Offline tests for the replay-driven quality evidence harness."""

from __future__ import annotations

import inspect
import json

import pytest

from skeleton.foundation.journal import EventJournal
from skeleton.quality.replay_evidence import (
    SCHEMA_ID,
    QualityEvidenceError,
    ReplayTape,
    ScenarioManifest,
    Verdict,
    evidence_digest_for,
    load_manifest,
    run_harness,
    snapshot_payload,
    verify_evidence,
)
from skeleton.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
    EvidenceKind,
    EvidenceRef,
)
from skeleton.school.replay import JeevesReplay, ReplaySnapshot, replay_digest


class ScriptedClock:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self._index = 0

    def __call__(self) -> float:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


def _tape(*steps: tuple[str, dict]) -> list[dict]:
    tape = ReplayTape()
    for kind, payload in steps:
        tape.append(kind, payload)
    return tape.export()


def _journal(*steps: tuple[str, dict]) -> list[dict]:
    journal = EventJournal()
    exported: list[dict] = []
    for index, (topic, payload) in enumerate(steps):
        entry = journal.append(topic, payload, timestamp=float(index))
        exported.append(
            {
                "topic": entry.topic,
                "payload": dict(entry.payload),
                "correlation_id": entry.correlation_id,
                "timestamp": entry.timestamp,
                "entry_hash": entry.entry_hash,
            }
        )
    return exported


def _ledger(action: str = "practice") -> DecisionLedger:
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "skill", "evidence"))
    ledger.append(
        session_id="s1",
        decision_id="d1",
        domain="test",
        action=action,
        evidence=("e1",),
        state={"mastery": 0.5},
        policy={"selected": action},
        disposition=DecisionDisposition.ACCEPTED,
    )
    return ledger


def _manifest(**overrides: object) -> ScenarioManifest:
    payload = {
        "schema": SCHEMA_ID,
        "scenario_id": "combat-baseline-001",
        "kind": "correctness",
        "source": "cognition.tape",
        "seed": 42,
        "max_runs": 2,
        "time_budget_ms": 1_000.0,
        "trace": _tape(("tick", {"n": 1}), ("tick", {"n": 2})),
        "tolerances": {"duration_ms": 0.0, "duration_rel": 0.0},
    }
    payload.update(overrides)
    return load_manifest(payload)


def test_manifest_roundtrip_is_deterministic() -> None:
    first = _manifest()
    second = load_manifest(json.loads(json.dumps(first.to_mapping())))
    assert first == second
    assert first.to_mapping()["schema"] == SCHEMA_ID


def test_unknown_schema_and_source_fail_closed() -> None:
    with pytest.raises(QualityEvidenceError, match="schema"):
        load_manifest({**_manifest().to_mapping(), "schema": "quality.replay_evidence.v0"})
    with pytest.raises(QualityEvidenceError, match="source"):
        load_manifest({**_manifest().to_mapping(), "source": "invented.core"})
    report = run_harness(
        {"schema": "nope", "scenario_id": "x", "kind": "correctness", "source": "cognition.tape", "trace": []}
    )
    assert report.verdict is Verdict.CORRUPT
    assert report.passed is False


def test_correctness_pass_is_repeatable_without_a_model() -> None:
    manifest = _manifest()
    first = run_harness(manifest)
    second = run_harness(manifest)
    assert first.verdict is Verdict.PASS
    assert first.passed is True
    assert first.runs == 2
    assert first.evidence_digest == second.evidence_digest
    assert first.trace_digests[0] == first.trace_digests[1] == first.baseline_digest


def test_harness_module_has_no_model_or_network_imports() -> None:
    import skeleton.quality.replay_evidence as module

    source = inspect.getsource(module)
    for token in ("openai", "anthropic", "httpx", "requests", "urllib", "socket"):
        assert token not in source
    assert "ReplayTape" in source and "ReplayEngine" in source and "JeevesReplay" in source


def test_regression_detection_fails_on_digest_change() -> None:
    baseline = _tape(("tick", {"n": 1}), ("tick", {"n": 2}))
    candidate = _tape(("tick", {"n": 1}), ("tick", {"n": 99}))
    report = run_harness(_manifest(kind="regression", max_runs=1, trace=baseline), candidate=candidate)
    assert report.verdict is Verdict.FAIL
    assert report.passed is False
    assert "baseline digest mismatch" in report.reasons
    assert report.trace_digests[0] != report.baseline_digest


def test_divergence_detected_via_existing_replay_tape() -> None:
    baseline = _tape(("tick", {"n": 1}), ("tick", {"n": 2}))
    candidate = _tape(("tick", {"n": 1}), ("tick", {"n": 3}))
    report = run_harness(
        _manifest(kind="divergence", max_runs=1, trace=baseline, expect_divergence_at=1),
        candidate=candidate,
    )
    assert report.verdict is Verdict.PASS
    assert report.divergence == {"sequence": 1, "reason": "cognition tape divergence"}

    missing = run_harness(_manifest(kind="divergence", max_runs=1, trace=baseline), candidate=baseline)
    assert missing.verdict is Verdict.FAIL
    assert "expected divergence was not observed" in missing.reasons

    wrong = run_harness(
        _manifest(kind="divergence", max_runs=1, trace=baseline, expect_divergence_at=0),
        candidate=candidate,
    )
    assert wrong.verdict is Verdict.FAIL
    assert "divergence sequence mismatch" in wrong.reasons


def test_tolerance_boundaries_are_inclusive() -> None:
    trace = _tape(("tick", {"n": 1}))
    inside = run_harness(
        _manifest(
            kind="performance",
            max_runs=1,
            trace=trace,
            expected_duration_ms=10.0,
            observed_duration_ms=[12.0],
            tolerances={"duration_ms": 1.0, "duration_rel": 0.1},
        )
    )
    assert inside.verdict is Verdict.PASS
    assert inside.envelope is not None
    assert inside.envelope["limit_ms"] == 2.0
    assert inside.envelope["within"] is True

    outside = run_harness(
        _manifest(
            kind="performance",
            max_runs=1,
            trace=trace,
            expected_duration_ms=10.0,
            observed_duration_ms=[12.1],
            tolerances={"duration_ms": 1.0, "duration_rel": 0.1},
        )
    )
    assert outside.verdict is Verdict.FAIL
    assert "performance envelope exceeded" in outside.reasons
    assert outside.passed is False


def test_corrupt_tape_fails_closed() -> None:
    events = _tape(("tick", {"n": 1}))
    events[0]["digest"] = "0" * 64
    report = run_harness(_manifest(max_runs=1, trace=events))
    assert report.verdict is Verdict.CORRUPT
    assert report.passed is False
    assert "corrupt cognition replay tape" in report.reasons


def test_corrupt_journal_hash_fails_closed() -> None:
    entries = _journal(("counter.tick", {"n": 1}))
    entries[0]["entry_hash"] = "f" * 64
    report = run_harness(_manifest(source="foundation.journal", max_runs=1, trace=entries))
    assert report.verdict is Verdict.CORRUPT
    assert "corrupt foundation journal trace" in report.reasons


def test_corrupt_evidence_digest_fails_closed() -> None:
    clean = run_harness(_manifest(max_runs=1))
    verified = verify_evidence(clean.to_mapping())
    assert verified.verdict is Verdict.PASS
    assert verified.evidence_digest == clean.evidence_digest

    tampered = clean.to_mapping()
    tampered["passed"] = False
    corrupt = verify_evidence(tampered)
    assert corrupt.verdict is Verdict.CORRUPT
    assert corrupt.passed is False
    assert "digest mismatch" in corrupt.reasons[0]

    body = dict(clean.to_mapping())
    body["verdict"] = "fail"
    body["passed"] = True
    body["evidence_digest"] = evidence_digest_for(body)
    disagree = verify_evidence(body)
    assert disagree.verdict is Verdict.CORRUPT
    assert "passed flag disagrees" in disagree.reasons[0]


def test_timeout_does_not_pass() -> None:
    report = run_harness(
        _manifest(max_runs=2, time_budget_ms=100.0),
        clock=ScriptedClock([0.0, 0.0, 5.0]),
    )
    assert report.verdict is Verdict.TIMEOUT
    assert report.passed is False
    assert report.runs == 1
    assert "time budget exceeded" in report.reasons


def test_repeatability_same_evidence_digest() -> None:
    manifest = _manifest(max_runs=3, seed=7)
    first = run_harness(manifest, clock=ScriptedClock([0.0] * 20))
    second = run_harness(manifest, clock=ScriptedClock([0.0] * 20))
    assert first.verdict is Verdict.PASS
    assert first.evidence_digest == second.evidence_digest
    assert json.dumps(first.to_mapping(), sort_keys=True) == json.dumps(second.to_mapping(), sort_keys=True)


def test_flaky_runs_are_quarantined_not_passed() -> None:
    left = _tape(("tick", {"n": 1}))
    right = _tape(("tick", {"n": 2}))
    report = run_harness(_manifest(max_runs=2, trace=left), candidates=[left, right])
    assert report.verdict is Verdict.QUARANTINE
    assert report.passed is False
    assert report.quarantine == {"reason": "non-reproducible results"}
    assert "non-reproducible digests" in report.reasons


def test_flaky_performance_is_quarantined() -> None:
    trace = _tape(("tick", {"n": 1}))
    report = run_harness(
        _manifest(
            kind="performance",
            max_runs=2,
            trace=trace,
            expected_duration_ms=10.0,
            observed_duration_ms=[10.0, 40.0],
            tolerances={"duration_ms": 1.0, "duration_rel": 0.0},
        )
    )
    assert report.verdict is Verdict.QUARANTINE
    assert report.passed is False
    assert "non-reproducible performance envelope" in report.reasons


def test_foundation_journal_adapter_consumes_replay_engine() -> None:
    trace = _journal(("counter.tick", {"n": 0}), ("counter.tick", {"n": 1}))
    report = run_harness(_manifest(source="foundation.journal", max_runs=2, trace=trace))
    assert report.verdict is Verdict.PASS
    assert report.source == "foundation.journal"
    shifted = _journal(("counter.tick", {"n": 0}), ("counter.tick", {"n": 9}))
    diverged = run_harness(
        _manifest(kind="regression", source="foundation.journal", max_runs=1, trace=trace),
        candidate=shifted,
    )
    assert diverged.verdict is Verdict.FAIL
    assert diverged.divergence is not None


def test_school_snapshot_adapter_consumes_jeeves_replay() -> None:
    left_ledger = _ledger("practice")
    right_ledger = _ledger("challenge")
    left = snapshot_payload(ReplaySnapshot.from_records(left_ledger.records))
    right = snapshot_payload(ReplaySnapshot.from_records(right_ledger.records))
    assert replay_digest(left_ledger.records) == replay_digest(left_ledger.records)
    assert not JeevesReplay().compare_snapshots(
        ReplaySnapshot.from_records(left_ledger.records),
        ReplaySnapshot.from_records(right_ledger.records),
    ).identical
    passed = run_harness(_manifest(source="school.snapshot", max_runs=2, trace=left))
    assert passed.verdict is Verdict.PASS
    failed = run_harness(
        _manifest(kind="regression", source="school.snapshot", max_runs=1, trace=left),
        candidate=right,
    )
    assert failed.verdict is Verdict.FAIL
    assert "baseline digest mismatch" in failed.reasons


def test_run_bounds_and_missing_trace_fail_closed() -> None:
    with pytest.raises(QualityEvidenceError, match="max_runs"):
        load_manifest({**_manifest().to_mapping(), "max_runs": 17})
    with pytest.raises(QualityEvidenceError, match="time_budget_ms"):
        load_manifest({**_manifest().to_mapping(), "time_budget_ms": 0})
    payload = _manifest().to_mapping()
    del payload["trace"]
    with pytest.raises(QualityEvidenceError, match="trace"):
        load_manifest(payload)
