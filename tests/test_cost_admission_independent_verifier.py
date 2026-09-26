from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_cost_admission_closure import (
    BOUNDARIES,
    MIRROR_PAIRS,
    REQUIRED_BUDGET_DIMENSIONS,
    verify_repository,
)


def _write_contract(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    payload = {
        "gap_register": [
            {
                "id": "gap-cost-admission",
                "status": "open",
            }
        ],
        "cost_admission_blueprint": {
            "budget_dimensions": sorted(REQUIRED_BUDGET_DIMENSIONS),
            "durable_quota": {
                "reference_backend": "skeleton/intelligence/quota_sqlite.py",
                "invariants": [
                    "reservation is idempotent",
                    "restart cannot erase quota",
                ],
            },
            "pressure": {
                "distributed": "shared durable atomic coordinator",
            },
            "closure_evidence": [
                "durable quota restart test",
                "multi-worker reservation race test",
                "actual usage reconciliation",
                "unknown-usage behavior",
                "no expensive provider/tool/storage path without admission receipt",
            ],
        },
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(payload),
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
        mirror = root / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())

    _write_contract(root)
    return root


def test_independent_cost_verifier_accepts_boundaries_and_mirrors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "cost-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "cost-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert receipt["blueprint_digest"]


def test_independent_cost_verifier_rejects_missing_boundary_token(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    target = root / "skeleton" / "skills" / "tool_runtime.py"
    target.write_text("# AdmissionRuntime\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "skeleton/skills/tool_runtime.py lost admission token: record_usage_event"
        in error
        for error in receipt["errors"]
    )


def test_independent_cost_verifier_rejects_ai_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton" / "ai" / "runtime" / "memory" / "projection.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical AI mirror drift: skeleton/memory/projection.py"
        in error
        for error in receipt["errors"]
    )


def test_independent_cost_verifier_rejects_missing_storage_budget_dimension(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    contract_path = root / "machine" / "ai_app_construction.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["cost_admission_blueprint"]["budget_dimensions"].remove("storage_bytes")
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "cost admission blueprint missing budget dimensions: storage_bytes"
        in error
        for error in receipt["errors"]
    )
