"""Completion percentages are scoped to signed plans, executable P1 and grade."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.report_ai_completion import audit_ai_delivery, DeliveryAuditError


def _write(root: Path, name: str, value: object) -> bytes:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    path.write_bytes(raw)
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    plan = {
        "volumes": [
            {"key": "VOL-000", "completion_checkbox": True, "enterprise_grade_state": "designed"},
            {"key": "VOL-001", "completion_checkbox": True, "enterprise_grade_state": "enterprise_qualified"},
        ],
    }
    ledger = {"records": [{"id": "ACC-VOL-000"}, {"id": "ACC-VOL-001"}]}
    plan_raw = _write(root, "machine/ai_master_plan.json", plan)
    ledger_raw = _write(root, "machine/ai_build_accountability.json", ledger)
    _write(root, "machine/ai_masterplan_parse_index.json", {
        "sources": {
            "machine/ai_master_plan.json": {"git_blob_sha": _sha(plan_raw)},
            "machine/ai_build_accountability.json": {"git_blob_sha": _sha(ledger_raw)},
        },
    })
    _write(root, "machine/ai_p1_task_backlog.json", {
        "tasks": [
            {"task_id": "P1-A", "status": "done", "completion_checkbox": True},
            {"task_id": "P1-B", "status": "blocked", "completion_checkbox": True},
        ],
    })
    _write(root, "machine/ai_p3_learning_closure.json", {
        "status": "active", "frontier": {"queued_volume_count": 5},
    })
    _write(root, "machine/ai_p3_training_closure.json", {"status": "candidate"})
    return root


def test_completion_report_does_not_conflate_signed_with_delivered(tmp_path: Path) -> None:
    report = audit_ai_delivery(_fixture(tmp_path))
    assert report["masterplan"]["signed_percent"] == 100
    assert report["masterplan"]["enterprise_qualified_percent"] == 50
    assert report["p1"]["done_percent"] == 50
    assert report["p1"]["signed_but_not_done"] == ["P1-B"]
    assert report["p3"]["deferred_volumes"] == 5
    assert report["index_fresh"]
    assert report["whole_project_completion_percent"] is None
    assert report["ready_for_full_completion"] is False
    assert len(report["open_obligations"]) >= 3


def test_stale_index_detected_and_not_accepted_as_current(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["volumes"][1]["completion_checkbox"] = False
    _write(root, "machine/ai_master_plan.json", plan)
    result = audit_ai_delivery(root)
    assert result["index_fresh"] is False
    assert result["masterplan"]["signed_percent"] == 50
    assert any("source identity mismatch" in issue for issue in result["open_obligations"])


def test_malformed_frontier_rejected_not_silently_counted(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    _write(root, "machine/ai_p3_learning_closure.json", {
        "status": "active", "frontier": {"queued_volume_count": True},
    })
    try:
        audit_ai_delivery(root)
    except DeliveryAuditError as exc:
        assert "deferred count" in str(exc)
    else:
        raise AssertionError("boolean deferred volume count must fail closed")


def test_live_completion_audit_reports_source_contradictions() -> None:
    repo = Path(__file__).resolve().parents[1]
    report = audit_ai_delivery(repo)
    assert report["masterplan"]["volumes_total"] == 421
    assert report["masterplan"]["signed"] <= 421
    assert report["p1"]["tasks_total"] == 44
    assert report["whole_project_completion_percent"] is None
