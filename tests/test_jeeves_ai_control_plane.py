import pytest

from skeleton.jeeves.ai.contracts import (
    Authority,
    ContractLedger,
    ContractRecord,
    ContractState,
    validate_contract,
)
from skeleton.jeeves.ai.evaluation import EvalLedger, EvalRecord, EvalState, validate_eval
from skeleton.jeeves.ai.orchestration import OrchestrRecord, OrchestrState, validate_orchestr


def test_contract_record_is_canonical_and_detached_from_input():
    payload = {"scope": "repo", "nested": {"x": 1}}
    record = ContractRecord("policy", ContractState.READY, payload, ("e1",))
    digest = record.digest
    payload["scope"] = "mutated"
    payload["nested"]["x"] = 2
    assert record.digest == digest
    assert record.payload["scope"] == "repo"
    assert validate_contract((record,)) == (digest,)


def test_contract_digest_ignores_mapping_insertion_order():
    left = ContractRecord("policy", payload={"a": 1, "b": 2})
    right = ContractRecord("policy", payload={"b": 2, "a": 1})
    assert left.digest == right.digest


def test_contract_rejects_nonfinite_and_unsupported_payloads():
    with pytest.raises(ValueError):
        ContractRecord("bad", payload={"score": float("nan")})
    with pytest.raises(ValueError):
        ContractRecord("bad", payload={"opaque": object()})


def test_contract_ledger_rejects_duplicate_names():
    record = ContractRecord("same")
    with pytest.raises(ValueError, match="duplicate"):
        ContractLedger((record, record))


def test_supervisor_secretary_worker_hierarchy_is_preserved():
    records = (
        OrchestrRecord("supervisor", authority=Authority.SUPERVISOR),
        OrchestrRecord("secretary", authority=Authority.SECRETARY, parent="supervisor"),
        OrchestrRecord("worker", authority=Authority.WORKER, parent="secretary"),
    )
    assert len(validate_orchestr(records)) == 3


def test_worker_cannot_parent_secretary_or_supervisor():
    records = (
        OrchestrRecord("worker", authority=Authority.WORKER),
        OrchestrRecord("secretary", authority=Authority.SECRETARY, parent="worker"),
    )
    with pytest.raises(ValueError, match="authority escalation"):
        validate_orchestr(records)


def test_secretary_cannot_parent_supervisor():
    records = (
        OrchestrRecord("secretary", authority=Authority.SECRETARY),
        OrchestrRecord("supervisor", authority=Authority.SUPERVISOR, parent="secretary"),
    )
    with pytest.raises(ValueError, match="authority escalation"):
        validate_orchestr(records)


def test_orchestration_requires_parent_and_dependencies_to_exist():
    with pytest.raises(ValueError, match="missing parent"):
        validate_orchestr((OrchestrRecord("worker", parent="missing"),))
    with pytest.raises(ValueError, match="missing dependency"):
        validate_orchestr((OrchestrRecord("worker", dependencies=("missing",)),))


def test_orchestration_rejects_dependency_cycles():
    records = (
        OrchestrRecord("a", dependencies=("b",)),
        OrchestrRecord("b", dependencies=("a",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_orchestr(records)


def test_orchestration_rejects_duplicate_names():
    record = OrchestrRecord("plan")
    with pytest.raises(ValueError, match="duplicate"):
        validate_orchestr((record, record))


def test_orchestration_payload_is_detached():
    payload = {"tool": "retrieval"}
    record = OrchestrRecord("plan", payload=payload)
    digest = record.digest
    payload["tool"] = "shell"
    assert record.digest == digest
    assert record.payload["tool"] == "retrieval"


def test_eval_requires_score_and_threshold_together():
    with pytest.raises(ValueError):
        EvalRecord("case", score=0.9)
    with pytest.raises(ValueError):
        EvalRecord("case", threshold=0.8)


def test_scored_eval_must_be_terminal():
    with pytest.raises(ValueError, match="terminal"):
        EvalRecord("case", state=EvalState.RUNNING, score=0.9, threshold=0.8)


def test_eval_pass_and_fail_are_explicit():
    passed = EvalRecord("pass", state=EvalState.DONE, score=0.9, threshold=0.8)
    below = EvalRecord("below", state=EvalState.DONE, score=0.7, threshold=0.8)
    failed = EvalRecord("failed", state=EvalState.FAILED, score=1.0, threshold=0.8)
    assert passed.passed is True
    assert below.passed is False
    assert failed.passed is False
    assert EvalLedger((passed, below, failed)).summary() == {"passed": 1, "failed": 2, "pending": 0}


def test_evaluation_identity_is_suite_plus_name():
    a = EvalRecord("case", suite="s1")
    b = EvalRecord("case", suite="s2")
    assert len(validate_eval((a, b))) == 2
    with pytest.raises(ValueError, match="duplicate"):
        validate_eval((a, a))


def test_state_surface_is_explicit():
    expected = {"new", "ready", "running", "blocked", "done", "failed"}
    assert {x.value for x in ContractState} == expected
    assert {x.value for x in OrchestrState} == expected
    assert {x.value for x in EvalState} == expected
