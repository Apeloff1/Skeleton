from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_stage7_golden_journeys import (
    BOUNDARIES,
    EXPECTED_DEPENDENCIES,
    MIRROR_PAIRS,
    verify_repository,
)


def _write_machine_contracts(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)

    handoff = {
        "entries": [
            {
                "gap": "gap-e2e-golden-journeys",
                "depends_on": sorted(EXPECTED_DEPENDENCIES),
                "implementation_status": "implementation-complete",
                "current_evidence": [
                    "prompt-only evidence",
                    "multi-turn evidence",
                    "approval-write evidence",
                    "approval renewal evidence",
                    "governance evidence",
                    "engine outage evidence",
                    "browser session evidence",
                ],
            }
        ]
    }
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(handoff),
        encoding="utf-8",
    )

    gap_rows = [{"id": "gap-e2e-golden-journeys", "status": "open"}]
    gap_rows.extend(
        {"id": gap_id, "status": "open"}
        for gap_id in sorted(EXPECTED_DEPENDENCIES)
    )
    construction = {
        "gap_register": gap_rows,
        "golden_journey_blueprint": {
            "gap": "gap-e2e-golden-journeys",
            "status": "implemented-pending-closure",
            "journeys": [
                {"id": "prompt-only"},
                {"id": "multi-turn"},
                {"id": "retrieval-grounded"},
                {"id": "read-tool"},
                {"id": "write-tool-with-approval"},
                {"id": "artifact"},
                {"id": "cancel"},
                {"id": "reconnect"},
                {"id": "provider-outage"},
                {"id": "engine-outage"},
                {"id": "governance-delete-export"},
            ],
        },
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )

    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                "# synthetic Stage-7 mirror source\n",
                encoding="utf-8",
            )
        mirror = root / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())

    _write_machine_contracts(root)
    return root


def test_stage7_verifier_accepts_complete_source_contracts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "stage7-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "stage7-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert set(receipt["dependency_graph"]) == EXPECTED_DEPENDENCIES


def test_stage7_verifier_rejects_missing_browser_reconnect_journey(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "frontend/scripts/test-operation-stream-session.mjs"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "# browser disconnect and reconnect resumes from persisted accepted cursor\n",
        "",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "lost Stage-7 token" in error
        and "browser disconnect and reconnect" in error
        for error in receipt["errors"]
    )


def test_stage7_verifier_rejects_approval_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton/ai/runtime/api/engine_service.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("canonical AI mirror drift" in error for error in receipt["errors"])


def test_stage7_verifier_rejects_dependency_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["depends_on"] = ["gap-streaming-protocol"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "Stage-7 dependency graph mismatch" in error
        for error in receipt["errors"]
    )


def test_stage7_verifier_rejects_premature_closed_gap(
    tmp_path: Path,
) -> None:
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


def test_stage7_verifier_rejects_blueprint_journey_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["golden_journey_blueprint"]["journeys"] = [
        item
        for item in payload["golden_journey_blueprint"]["journeys"]
        if item["id"] != "governance-delete-export"
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "golden journey blueprint missing journeys" in error
        and "governance-delete-export" in error
        for error in receipt["errors"]
    )
