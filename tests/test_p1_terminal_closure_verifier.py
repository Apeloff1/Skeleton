from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_p1_terminal_closure import (
    EXPECTED_P1_GAPS,
    verify_repository,
)


def _valid_repo(tmp_path: Path) -> Path:
    machine = tmp_path / "machine"
    machine.mkdir(parents=True)
    payload = {
        "gap_register": [
            {
                "id": gap_id,
                "priority": "P1",
                "status": "closed",
                "outstanding_evidence": [],
            }
            for gap_id in sorted(EXPECTED_P1_GAPS)
        ],
        "provider_redundancy_blueprint": {
            "gap": "gap-provider-redundancy",
            "status": "closed",
        },
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return tmp_path


def test_p1_terminal_verifier_accepts_closed_inventory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "p1-terminal-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "p1-terminal-head"
    assert receipt["actual_gap_count"] == 3
    assert set(receipt["gap_state"]) == EXPECTED_P1_GAPS


def test_p1_terminal_verifier_rejects_reopened_gap(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("must remain closed" in error for error in receipt["errors"])


def test_p1_terminal_verifier_rejects_inventory_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"].append(
        {
            "id": "gap-unexpected-p1",
            "priority": "P1",
            "status": "closed",
            "outstanding_evidence": [],
        }
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("P1 inventory mismatch" in error for error in receipt["errors"])


def test_p1_terminal_verifier_rejects_redundancy_blueprint_regression(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["provider_redundancy_blueprint"]["status"] = (
        "implemented-pending-closure"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "blueprint must remain closed" in error
        for error in receipt["errors"]
    )
