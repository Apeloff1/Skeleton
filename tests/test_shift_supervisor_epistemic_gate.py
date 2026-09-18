from __future__ import annotations

from core.shift_supervisor.epistemic_gate import EpistemicExecutionGate


def _task(**overrides):
    task = {
        "title": "Ready task",
        "expected_output": "A bounded implementation and regression proof",
        "validation": ["focused regression", "integration smoke"],
        "_planning_council": {
            "version": 2,
            "decision": "accept",
            "confidence": 90,
            "roles": {},
            "assumptions": ["current main is the integration baseline"],
            "failure_modes": ["contract mismatch"],
            "success_metrics": ["all focused and integration checks pass"],
            "evidence_gaps": [],
        },
    }
    task.update(overrides)
    return task


def test_gate_admits_execution_ready_reviewed_task(monkeypatch):
    monkeypatch.setenv("SHIFT_EPISTEMIC_GATE", "1")
    accepted = EpistemicExecutionGate().filter_tasks([_task()])

    assert len(accepted) == 1
    evidence = accepted[0]["_epistemic_gate"]
    assert evidence["status"] == "ready"
    assert evidence["checks"] == {
        "confidence": True,
        "expected_output": True,
        "validation": True,
        "failure_analysis": True,
        "falsifiable_success": True,
        "evidence_gap_budget": True,
    }


def test_gate_blocks_low_confidence_review(monkeypatch):
    monkeypatch.setenv("SHIFT_EPISTEMIC_MIN_CONFIDENCE", "70")
    task = _task()
    task["_planning_council"]["confidence"] = 69
    assert EpistemicExecutionGate().filter_tasks([task]) == []


def test_gate_blocks_non_falsifiable_or_unvalidated_work():
    for override in (
        {"expected_output": ""},
        {"validation": []},
    ):
        assert EpistemicExecutionGate().filter_tasks([_task(**override)]) == []

    no_failure = _task()
    no_failure["_planning_council"]["failure_modes"] = []
    assert EpistemicExecutionGate().filter_tasks([no_failure]) == []

    no_metric = _task()
    no_metric["_planning_council"]["success_metrics"] = []
    assert EpistemicExecutionGate().filter_tasks([no_metric]) == []


def test_gate_blocks_excessive_open_evidence_gaps(monkeypatch):
    monkeypatch.setenv("SHIFT_EPISTEMIC_MAX_GAPS", "2")
    task = _task()
    task["_planning_council"]["evidence_gaps"] = ["a", "b", "c"]
    assert EpistemicExecutionGate().filter_tasks([task]) == []


def test_gate_leaves_unreviewed_budget_overflow_unchanged():
    task = {"title": "overflow", "target_team": "idle"}
    assert EpistemicExecutionGate().filter_tasks([task]) == [task]


def test_gate_disable_switch_is_reversible(monkeypatch):
    monkeypatch.setenv("SHIFT_EPISTEMIC_GATE", "0")
    weak = _task(expected_output="", validation=[])
    weak["_planning_council"]["confidence"] = 0
    assert EpistemicExecutionGate().filter_tasks([weak]) == [weak]


def test_gate_environment_bounds_are_clamped(monkeypatch):
    monkeypatch.setenv("SHIFT_EPISTEMIC_MIN_CONFIDENCE", "999")
    monkeypatch.setenv("SHIFT_EPISTEMIC_MAX_GAPS", "999")
    gate = EpistemicExecutionGate()
    assert gate.min_confidence() == 100
    assert gate.max_evidence_gaps() == 16
