from __future__ import annotations

import json

from scripts import check_ai_build_accountability as checker


def _load() -> dict:
    return json.loads(checker.LEDGER.read_text(encoding="utf-8"))


def test_accountability_ledger_is_valid() -> None:
    assert checker.validate() == []


def test_accountability_tracks_every_plan_build_surface() -> None:
    ledger = _load()
    master = json.loads(checker.MASTER.read_text(encoding="utf-8"))
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    assert ledger["tracked_counts"] == {
        "volumes": 421,
        "work_packages": 31,
        "queue_tasks": len(queue["tasks"]),
        "vertical_slices": len(master["vertical_slices"]),
        "total": 421 + 31 + len(queue["tasks"]) + len(master["vertical_slices"]),
    }
    assert all(record["signing_required"] is True for record in ledger["records"])


def test_no_completion_checkbox_is_checked_without_two_signoffs() -> None:
    ledger = _load()
    for record in ledger["records"]:
        if record["checkbox"]:
            assert record["implementation_signoff"]["signed"] is True
            assert record["verification_signoff"]["signed"] is True
            assert record["completed_at_utc"]


def test_current_pending_queue_has_no_fabricated_signatures() -> None:
    ledger = _load()
    queue = json.loads(checker.QUEUE.read_text(encoding="utf-8"))
    by_id = {record["id"]: record for record in ledger["records"]}
    for task in queue["tasks"]:
        if task["status"] == "pending":
            record = by_id[task["accountability_id"]]
            assert record["checkbox"] is False
            assert record["implementation_signoff"]["signed"] is False
            assert record["verification_signoff"]["signed"] is False


def test_visible_checkboxes_match_machine_ledger() -> None:
    ledger = _load()
    visible = {
        rid: mark
        for mark, rid in checker.CHECK_RE.findall(checker.HUMAN.read_text(encoding="utf-8"))
    }
    assert len(visible) == len(ledger["records"])
    for record in ledger["records"]:
        assert visible[record["id"]] == ("x" if record["checkbox"] else " ")
