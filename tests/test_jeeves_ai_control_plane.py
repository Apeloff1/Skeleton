import pytest
from collections.abc import Mapping

from skeleton.jeeves.ai.contracts import Authority, ContractLedger, ContractRecord, ContractState, validate_contract
from skeleton.jeeves.ai.evaluation import EvalLedger, EvalRecord, EvalState, validate_eval
from skeleton.jeeves.ai.orchestration import OrchestrLedger, OrchestrRecord, OrchestrState, validate_orchestr


class _DuplicateItemsMapping(Mapping):
    """Adversarial Mapping whose items() violates unique-key mapping semantics."""

    def __getitem__(self, key):
        if key == "scope":
            return "first"
        raise KeyError(key)

    def __iter__(self):
        return iter(("scope",))

    def __len__(self):
        return 1

    def items(self):
        return (("scope", "first"), ("scope", "second"))


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
    assert ContractRecord("policy", payload={"a": 1, "b": 2}).digest == ContractRecord("policy", payload={"b": 2, "a": 1}).digest


def test_all_planes_share_fail_closed_json_contract():
    constructors = (ContractRecord, EvalRecord, OrchestrRecord)
    for constructor in constructors:
        with pytest.raises(ValueError):
            constructor("bad", payload={"score": float("nan")})
        with pytest.raises(ValueError):
            constructor("bad", payload={"opaque": object()})
        with pytest.raises(ValueError):
            constructor("bad", payload={"nul": "a\x00b"})


def test_all_planes_reject_adversarial_duplicate_mapping_items():
    payload = _DuplicateItemsMapping()
    for constructor in (ContractRecord, EvalRecord, OrchestrRecord):
        with pytest.raises(ValueError, match="duplicate JSON key"):
            constructor("duplicate-key", payload=payload)


def test_all_planes_reject_excessive_nesting():
    value = "leaf"
    for _ in range(14):
        value = {"x": value}
    for constructor in (ContractRecord, EvalRecord, OrchestrRecord):
        with pytest.raises(ValueError, match="nesting"):
            constructor("deep", payload={"root": value})


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
    records = (OrchestrRecord("worker", authority=Authority.WORKER), OrchestrRecord("secretary", authority=Authority.SECRETARY, parent="worker"))
    with pytest.raises(ValueError, match="authority escalation"):
        validate_orchestr(records)


def test_secretary_cannot_parent_supervisor():
    records = (OrchestrRecord("secretary", authority=Authority.SECRETARY), OrchestrRecord("supervisor", authority=Authority.SUPERVISOR, parent="secretary"))
    with pytest.raises(ValueError, match="authority escalation"):
        validate_orchestr(records)


def test_orchestration_requires_parent_and_dependencies_to_exist():
    with pytest.raises(ValueError, match="missing parent"):
        validate_orchestr((OrchestrRecord("worker", parent="missing"),))
    with pytest.raises(ValueError, match="missing dependency"):
        validate_orchestr((OrchestrRecord("worker", dependencies=("missing",)),))


def test_dependency_edges_cannot_escalate_authority():
    worker_to_secretary = (
        OrchestrRecord("secretary", authority=Authority.SECRETARY),
        OrchestrRecord("worker", authority=Authority.WORKER, dependencies=("secretary",)),
    )
    with pytest.raises(ValueError, match="dependency authority escalation"):
        validate_orchestr(worker_to_secretary)

    secretary_to_supervisor = (
        OrchestrRecord("supervisor", authority=Authority.SUPERVISOR),
        OrchestrRecord("secretary", authority=Authority.SECRETARY, dependencies=("supervisor",)),
    )
    with pytest.raises(ValueError, match="dependency authority escalation"):
        validate_orchestr(secretary_to_supervisor)


def test_dependency_edges_allow_same_or_lower_authority():
    records = (
        OrchestrRecord("worker", authority=Authority.WORKER),
        OrchestrRecord("secretary", authority=Authority.SECRETARY, dependencies=("worker",)),
        OrchestrRecord("supervisor", authority=Authority.SUPERVISOR, dependencies=("secretary", "worker")),
    )
    assert len(validate_orchestr(records)) == 3


def test_orchestration_rejects_dependency_cycles():
    with pytest.raises(ValueError, match="cycle"):
        validate_orchestr((OrchestrRecord("a", dependencies=("b",)), OrchestrRecord("b", dependencies=("a",))))


def test_orchestration_rejects_parent_cycles():
    with pytest.raises(ValueError, match="cycle"):
        validate_orchestr((OrchestrRecord("a", parent="b"), OrchestrRecord("b", parent="a")))


def test_orchestration_ledger_requires_tuple_and_rejects_duplicate_names():
    with pytest.raises(ValueError, match="tuple"):
        OrchestrLedger([])  # type: ignore[arg-type]
    record = OrchestrRecord("plan")
    with pytest.raises(ValueError, match="duplicate"):
        validate_orchestr((record, record))


def test_orchestration_payload_is_detached():
    payload = {"tool": "retrieval", "nested": {"mode": "read"}}
    record = OrchestrRecord("plan", payload=payload)
    digest = record.digest
    payload["tool"] = "shell"
    payload["nested"]["mode"] = "write"
    assert record.digest == digest
    assert record.payload["tool"] == "retrieval"
    assert record.payload["nested"]["mode"] == "read"


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


def test_shared_canonicalization_is_order_stable_across_planes():
    assert EvalRecord("case", payload={"a": 1, "b": 2}).digest == EvalRecord("case", payload={"b": 2, "a": 1}).digest
    assert OrchestrRecord("task", payload={"a": 1, "b": 2}).digest == OrchestrRecord("task", payload={"b": 2, "a": 1}).digest


def test_state_surface_is_explicit():
    expected = {"new", "ready", "running", "blocked", "done", "failed"}
    assert {x.value for x in ContractState} == expected
    assert {x.value for x in OrchestrState} == expected
    assert {x.value for x in EvalState} == expected
