from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_golden_journey_closure import (
    EXPECTED_DEPENDENCIES,
    JOURNEY_SURFACES,
    REQUIRED_CLOSURE_EVIDENCE,
    verify_repository,
)


def _write_machine_contracts(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)

    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "gap": "gap-e2e-golden-journeys",
                        "depends_on": sorted(EXPECTED_DEPENDENCIES),
                        "implementation_status": "implemented_pending_closure",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    gaps = [
        {
            "id": "gap-e2e-golden-journeys",
            "status": "open",
            "closure_evidence": sorted(REQUIRED_CLOSURE_EVIDENCE),
        }
    ]
    gaps.extend(
        {"id": gap, "status": "open"}
        for gap in sorted(EXPECTED_DEPENDENCIES)
    )
    (machine / "ai_app_construction.json").write_text(
        json.dumps({"gap_register": gaps}),
        encoding="utf-8",
    )

    (machine / "ai_closure_evidence.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "gap": "gap-e2e-golden-journeys",
                        "implementation_state": "implemented_pending_closure",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    for rel, tokens in JOURNEY_SURFACES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )
    _write_machine_contracts(tmp_path)
    return tmp_path


def test_golden_journey_verifier_accepts_complete_surface(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "golden-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "golden-head"
    assert len(receipt["journey_digests"]) == len(JOURNEY_SURFACES)
    assert set(receipt["dependency_graph"]) == EXPECTED_DEPENDENCIES


def test_golden_journey_verifier_rejects_missing_browser_race(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "frontend/scripts/test-operation-stream-session.mjs"
    path.write_text("# disconnect and reconnect\n# slow browser recovers\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("cancel-complete race" in error for error in receipt["errors"])


def test_golden_journey_verifier_rejects_dependency_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["depends_on"] = ["gap-streaming-protocol"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("dependency graph mismatch" in error for error in receipt["errors"])


def test_closed_stage7_rejects_open_dependencies(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "closed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "closed Stage-7 gap has non-closed dependencies" in error
        for error in receipt["errors"]
    )
