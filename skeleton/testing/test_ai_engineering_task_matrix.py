from __future__ import annotations

import json

from scripts import check_ai_engineering_task_matrix as checker


def test_engineering_task_matrix_is_complete() -> None:
    assert checker.validate() == []
    matrix = json.loads(checker.MATRIX.read_text(encoding="utf-8"))
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    assert len(matrix["tasks"]) == len(queue["tasks"]) == 42
    assert [x["task_id"] for x in matrix["tasks"]] == [
        x["task_id"] for x in queue["tasks"]
    ]


def test_each_task_inherits_engineering_overlay() -> None:
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    for task in queue["tasks"]:
        assert "engineering_task_matrix" in task["acceptance_overlays"]
        inheritance = task["engineering_inheritance"]
        assert inheritance["task_id"] == task["task_id"]
        assert inheritance["engineering_profile_refs"] == task["work_package_refs"]


def test_task_matrix_has_failure_recovery_and_budget_obligations() -> None:
    matrix = json.loads(checker.MATRIX.read_text(encoding="utf-8"))
    for task in matrix["tasks"]:
        assert task["required_dimensions"], task["task_id"]
        assert task["nfr_budget_classes"], task["task_id"]
        assert task["principal_failure_modes"], task["task_id"]
        assert task["recovery_requirements"], task["task_id"]
        assert task["evidence_modes"], task["task_id"]


def test_empty_evidence_cannot_claim_complete_engineering_gate() -> None:
    matrix = json.loads(checker.MATRIX.read_text(encoding="utf-8"))
    assert all(
        task["engineering_gate_state"] == "obligations_bound_evidence_pending"
        for task in matrix["tasks"]
        if not task["engineering_evidence_refs"] and not task["budget_binding_refs"]
    )
