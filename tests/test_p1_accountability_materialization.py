from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_accountability_tool():
    path = ROOT / "scripts" / "ai_accountability.py"
    spec = importlib.util.spec_from_file_location(
        "ai_accountability_under_test",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_p1_tasks_have_materialized_accountability_records() -> None:
    backlog = json.loads(
        (ROOT / "machine" / "ai_p1_task_backlog.json").read_text(
            encoding="utf-8"
        )
    )
    ledger = json.loads(
        (ROOT / "machine" / "ai_build_accountability.json").read_text(
            encoding="utf-8"
        )
    )
    records = {
        row["id"]: row
        for row in ledger["records"]
        if row["type"] == "p1_task"
    }

    assert len(backlog["tasks"]) == 44
    assert len(records) == 44
    assert ledger["tracked_counts"]["p1_tasks"] == 44
    assert ledger["tracked_counts"]["total"] == len(ledger["records"])

    for task in backlog["tasks"]:
        rid = task["accountability_ref"]
        assert rid == f"ACC-{task['task_id']}"
        assert rid in records

        record = records[rid]
        assert record["baseline_status"] == "planned"
        assert task["accountability_status"] == record["status"]
        assert task["completion_checkbox"] == record["checkbox"]
        assert task["completion_checkbox_mark"] == record["checkbox_mark"]
        assert task["implementation_signed"] == bool(
            record["implementation_signoff"]["signed"]
        )
        assert task["verification_signed"] == bool(
            record["verification_signoff"]["signed"]
        )

        if record["status"] == record["baseline_status"]:
            assert record["history"] == []
        else:
            assert record["history"]
            assert record["history"][-1]["to_status"] == record["status"]


def test_scheduling_state_is_separate_from_signed_accountability_state() -> None:
    backlog = json.loads(
        (ROOT / "machine" / "ai_p1_task_backlog.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {task["task_id"]: task for task in backlog["tasks"]}

    assert by_id["P1-EVID-01"]["status"] == "ready"
    assert by_id["P1-EVID-02"]["status"] == "blocked"

    for task in backlog["tasks"]:
        assert task["accountability_required"] is True
        assert task["status"] in {"ready", "blocked"}
        assert task["accountability_status"] in {
            "planned",
            "in_progress",
            "evidence_pending",
            "done",
        }
        assert task["completion_checkbox_mark"] == (
            "[x]" if task["completion_checkbox"] else "[ ]"
        )
        if task["verification_signed"]:
            assert task["implementation_signed"] is True
        if task["completion_checkbox"]:
            assert task["implementation_signed"] is True
            assert task["verification_signed"] is True
            assert task["accountability_status"] == "done"


def test_accountability_lifecycle_maps_p1_tasks_like_executable_tasks() -> None:
    module = _load_accountability_tool()
    record = {"type": "p1_task"}

    assert module.type_status(record, "start") == "in_progress"
    assert module.type_status(record, "implementation") == "evidence_pending"
    assert module.type_status(record, "verification") == "evidence_pending"
    assert module.type_status(record, "complete") == "done"


def test_human_ledger_exposes_every_p1_accountability_checkbox() -> None:
    backlog = json.loads(
        (ROOT / "machine" / "ai_p1_task_backlog.json").read_text(
            encoding="utf-8"
        )
    )
    human = (
        ROOT / "docs" / "plan" / "BUILD_ACCOUNTABILITY_LEDGER.md"
    ).read_text(encoding="utf-8")

    assert "## P1 Trustworthy-Production Tasks" in human
    assert "44 P1 tasks" in human
    for task in backlog["tasks"]:
        marker = (
            task["completion_checkbox_mark"]
            + " "
            + chr(96)
            + task["accountability_ref"]
            + chr(96)
        )
        assert marker in human


def test_canonical_accountability_validator_accepts_p1_records() -> None:
    path = ROOT / "scripts" / "check_ai_build_accountability.py"
    spec = importlib.util.spec_from_file_location(
        "check_ai_build_accountability_under_test",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.validate() == []
