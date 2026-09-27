from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_masterplan_completion import (
    EXPECTED_GAPS,
    P0_GAPS,
    REQUIRED_BLUEPRINTS,
    verify_repository,
)


def _valid_repo(tmp_path: Path) -> Path:
    machine = tmp_path / "machine"
    machine.mkdir(parents=True)

    gaps = [
        {
            "id": gap_id,
            "priority": "P1" if gap_id not in P0_GAPS else "P0",
            "status": "closed",
            "outstanding_evidence": [],
        }
        for gap_id in sorted(EXPECTED_GAPS)
    ]
    construction = {"gap_register": gaps}
    for name, gap_id in REQUIRED_BLUEPRINTS.items():
        construction[name] = {
            "schema_version": 1,
            "status": "closed",
            "gap": gap_id,
        }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction),
        encoding="utf-8",
    )

    handoff = {
        "entries": [
            {
                "gap": gap_id,
                "implementation_status": "closed",
                "remaining": [],
                "blockers": [],
            }
            for gap_id in sorted(P0_GAPS)
        ]
    }
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(handoff),
        encoding="utf-8",
    )

    closure = {
        "entries": [
            {
                "gap": gap_id,
                "gap_status": "closed",
                "implementation_state": "closed",
                "closure_decision": "closed",
                "outstanding_evidence": [],
                "blockers": [],
            }
            for gap_id in sorted(P0_GAPS)
        ]
    }
    (machine / "ai_closure_evidence.json").write_text(
        json.dumps(closure),
        encoding="utf-8",
    )
    return tmp_path


def test_completion_verifier_accepts_terminal_masterplan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "terminal-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "terminal-head"
    assert receipt["actual_gap_count"] == len(EXPECTED_GAPS)
    assert receipt["open_gaps"] == []
    assert receipt["handoff_gap_count"] == len(P0_GAPS)
    assert receipt["closure_gap_count"] == len(P0_GAPS)
    assert receipt["blueprint_count"] == len(REQUIRED_BLUEPRINTS)


def test_completion_verifier_rejects_open_gap(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert receipt["open_gaps"]
    assert any("open masterplan gaps remain" in item for item in receipt["errors"])


def test_completion_verifier_rejects_missing_gap_inventory(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"].pop()
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("canonical gap inventory mismatch" in item for item in receipt["errors"])


def test_completion_verifier_rejects_missing_p0_handoff(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"].pop()
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("P0 implementation handoffs missing" in item for item in receipt["errors"])


def test_completion_verifier_rejects_nonterminal_blueprint(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    first = next(iter(REQUIRED_BLUEPRINTS))
    payload[first]["status"] = "implemented-pending-closure"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("non-terminal status" in item for item in receipt["errors"])


def test_completion_verifier_rejects_outstanding_closure_evidence(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_closure_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["outstanding_evidence"] = ["still open"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "closure still has outstanding_evidence" in item
        for item in receipt["errors"]
    )

def test_completion_verifier_rejects_closed_gap_with_pending_machine_state(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["verification_state"] = "pending-exact-head"
    payload["gap_register"][0]["progress"] = {
        "state": "implemented_pending_closure",
        "remaining": ["collect exact-head evidence"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("verification_state" in item for item in receipt["errors"])
    assert any("progress.state" in item for item in receipt["errors"])
    assert any("progress.remaining" in item for item in receipt["errors"])

