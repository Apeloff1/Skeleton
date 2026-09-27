from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_ai_masterplan_final_closure import (
    EXPECTED_DEPENDENCIES,
    EXPECTED_GAPS,
    verify_repository,
)


def _write_valid_repo(root: Path) -> Path:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)

    gaps = []
    handoff = []
    evidence = []
    construction: dict[str, object] = {"gap_register": gaps}

    for index, gap_id in enumerate(EXPECTED_GAPS):
        gaps.append({"id": gap_id, "status": "closed"})
        handoff.append(
            {
                "gap": gap_id,
                "implementation_status": "closed",
                "remaining": [],
                "depends_on": list(EXPECTED_DEPENDENCIES[gap_id]),
            }
        )
        evidence.append(
            {
                "gap": gap_id,
                "gap_status": "closed",
                "implementation_state": "closed",
                "closure_decision": "closed",
                "outstanding_evidence": [],
                "blockers": [],
            }
        )
        construction[f"blueprint_{index}"] = {
            "gap": gap_id,
            "status": "closed",
            "remaining": [],
        }

    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction),
        encoding="utf-8",
    )
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps({"entries": handoff}),
        encoding="utf-8",
    )
    (machine / "ai_closure_evidence.json").write_text(
        json.dumps({"entries": evidence}),
        encoding="utf-8",
    )
    return root


def test_final_closure_accepts_all_closed_consistent_graph(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _write_valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "final-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "final-head"
    assert receipt["closed_gap_count"] == len(EXPECTED_GAPS)
    assert receipt["expected_gap_count"] == len(EXPECTED_GAPS)
    assert set(receipt["rows"]) == set(EXPECTED_GAPS)
    assert len(receipt["contract_digests"]) == 3


def test_final_closure_rejects_open_gap(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("construction status is not closed" in e for e in receipt["errors"])


def test_final_closure_rejects_stale_blocker(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_closure_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["blockers"] = ["stale blocker"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("non-empty blockers" in e for e in receipt["errors"])


def test_final_closure_rejects_remaining_handoff_work(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["remaining"] = ["unfinished"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("non-empty remaining" in e for e in receipt["errors"])


def test_final_closure_rejects_missing_blueprint(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("blueprint_0")
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("has no associated blueprint/contract" in e for e in receipt["errors"])


def test_final_closure_rejects_nonclosed_blueprint(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["blueprint_0"]["status"] = "implemented-pending-closure"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("blueprint blueprint_0 is not closed" in e for e in receipt["errors"])


def test_final_closure_rejects_unknown_dependency(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][-1]["depends_on"] = ["gap-unknown"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("has unknown dependencies" in e for e in receipt["errors"])


def test_final_closure_rejects_dependency_cycle(tmp_path: Path) -> None:
    root = _write_valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["depends_on"] = [EXPECTED_GAPS[1]]
    payload["entries"][1]["depends_on"] = [EXPECTED_GAPS[0]]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("dependency graph contains cycle" in e for e in receipt["errors"])
