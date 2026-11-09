from __future__ import annotations

import json
from pathlib import Path

from scripts.check_p1_terminal_closure_manifest import validate_repository


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "machine/ai_p1_terminal_closure.json",
        {
            "schema_version": 1,
            "status": "closed",
            "claim_scope": "bounded_trustworthy_production_frontier",
            "frontier": {
                "masterplan_volume_count": 421,
                "primary_p1_frontier_volume_count": 107,
                "deferred_to_p2_volume_count": 314,
            },
            "risk_evidence": {
                "required_obligation_count": 513,
                "required_disposition": "evidence",
                "required_blocking_count": 0,
                "required_unclassified_count": 0,
                "accepted_risk_allowed": False,
            },
            "planning_ledger_semantics": {
                "execution_map_status": "active",
                "task_backlog_status": "active",
            },
            "handoff": {
                "next_phase": "P2",
                "expected_volume_count": 314,
            },
        },
    )
    _write(
        tmp_path / "machine/ai_p1_execution_map.json",
        {
            "status": "active",
            "scope_summary": {
                "masterplan_volume_count": 421,
                "primary_p1_frontier_volume_count": 107,
                "deferred_volume_count": 314,
                "deferred_volume_refs": [f"VOL-{index:03d}" for index in range(1, 315)],
            },
        },
    )
    _write(
        tmp_path / "machine/p1_risk_evidence_bindings.json",
        {
            "records": [
                {
                    "obligation_id": f"obligation-{index}",
                    "disposition": "evidence",
                    "evidence": [{"source": f"receipt-{index}"}],
                    "accepted_risk": None,
                }
                for index in range(513)
            ]
        },
    )
    _write(
        tmp_path / "machine/ai_app_construction.json",
        {
            "gap_register": [
                {
                    "id": gap,
                    "priority": "P1",
                    "status": "closed",
                    "outstanding_evidence": [],
                }
                for gap in (
                    "gap-feedback-promotion",
                    "gap-provider-redundancy",
                    "gap-release-slo-loop",
                )
            ],
            "provider_redundancy_blueprint": {
                "gap": "gap-provider-redundancy",
                "status": "closed",
            },
        },
    )
    return tmp_path


def test_terminal_manifest_accepts_closed_frontier(tmp_path: Path) -> None:
    errors, report = validate_repository(_repo(tmp_path))
    assert errors == []
    assert report["valid"] is True
    assert report["p1_frontier"] == "107/107"
    assert report["risk_obligations"] == "513/513"


def test_terminal_manifest_rejects_non_evidence_obligation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "machine/p1_risk_evidence_bindings.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][3]["disposition"] = "unclassified"
    _write(path, payload)

    errors, report = validate_repository(root)
    assert report["valid"] is False
    assert any("not evidence-closed" in error for error in errors)


def test_terminal_manifest_rejects_scope_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "machine/ai_p1_execution_map.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["scope_summary"]["deferred_volume_count"] = 313
    _write(path, payload)

    errors, _ = validate_repository(root)
    assert any("scope partition drift" in error for error in errors)
