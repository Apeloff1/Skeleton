from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.build_p1_risk_classification_evidence_batch1 import (
    COVERAGE,
    RiskClassificationEvidenceError,
    build_risk_classification_evidence,
)
from scripts.reconcile_p1_risk_evidence import (
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
)

ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40

EXPECTED_RISKS = {
    ("VOL-000", "human/machine plan divergence"),
    ("VOL-000", "status inflation without evidence"),
    ("VOL-000", "parallel planning systems bypassing canonical authority"),
    ("VOL-038", "canonicalization mismatch"),
    ("VOL-038", "missing lineage edge"),
    ("VOL-038", "signature detached from semantic content"),
    ("VOL-056", "orphan gaps"),
    ("VOL-056", "status inflation"),
    ("VOL-056", "duplicate/conflicting records"),
    ("VOL-057", "critical risk hidden by aggregate status"),
    ("VOL-057", "stale risk owner"),
    ("VOL-057", "paper control without evidence"),
}


def _copy(root: Path, relative: Path) -> None:
    source = ROOT / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    required = {MASTER, P1_MAP, ADVERSARIAL, POLICY, REGISTRY}
    for spec in COVERAGE.values():
        required.update(Path(item) for item in spec["sources"])
        required.update(Path(item) for item in spec["tests"])
    for relative in sorted(required, key=str):
        _copy(root, relative)
    return root


def test_live_batch_is_bounded_high_severity_and_non_authoritative() -> None:
    report = build_risk_classification_evidence(ROOT, expected_head=HEAD)

    assert set(COVERAGE) == EXPECTED_RISKS
    assert report["covered_risk_count"] == 12
    assert report["covered_volume_count"] == 4
    assert report["already_bound_count"] == 12
    assert report["candidate_binding_count"] == 0
    assert report["recommended_severity"] == "high"
    assert report["recommended_disposition"] == "evidence"
    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["lowers_severity"] is False
    assert report["clears_source_risks"] is False
    assert report["promotes_maturity"] is False

    rows = report["records"]
    assert {(row["volume_key"], row["statement"]) for row in rows} == EXPECTED_RISKS
    assert len({row["obligation_id"] for row in rows}) == 12
    assert all(row["binding_present"] is True for row in rows)
    assert all(row["recommended_severity"] == "high" for row in rows)
    assert all(row["recommended_disposition"] == "evidence" for row in rows)
    assert all(
        row["candidate_evidence_ref"]["digest"] == row["packet_digest"]
        for row in rows
    )
    assert all(
        row["candidate_evidence_ref"]["source"].endswith(":" + HEAD)
        for row in rows
    )


def test_builder_does_not_mutate_registry_or_masterplan() -> None:
    before_registry = (ROOT / REGISTRY).read_bytes()
    before_master = (ROOT / MASTER).read_bytes()
    build_risk_classification_evidence(ROOT, expected_head=HEAD)
    assert (ROOT / REGISTRY).read_bytes() == before_registry
    assert (ROOT / MASTER).read_bytes() == before_master


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_invalid_exact_head_fails_closed(head: str) -> None:
    with pytest.raises(
        RiskClassificationEvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_risk_classification_evidence(ROOT, expected_head=head)


def test_missing_contract_path_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    (root / "skeleton/contracts/promotion_evidence.py").unlink()
    with pytest.raises(RiskClassificationEvidenceError, match="evidence path is missing"):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_missing_contract_marker_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    path = root / "skeleton/contracts/risk_evidence.py"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "evidence disposition requires evidence",
            "evidence requirement drifted",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(RiskClassificationEvidenceError, match="missing contract markers"):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_canonical_risk_statement_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"] = [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] != "risk_control_evidence"
    ]
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    path = root / MASTER
    master = json.loads(path.read_text(encoding="utf-8"))
    volume = next(row for row in master["volumes"] if row["key"] == "VOL-000")
    volume["risks"].remove("human/machine plan divergence")
    path.write_text(json.dumps(master, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="missing canonical risk obligation",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_existing_binding_is_detected_without_rewrite(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"] = [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] != "risk_control_evidence"
    ]
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    baseline = build_risk_classification_evidence(root, expected_head=HEAD)
    assert baseline["already_bound_count"] == 0
    assert baseline["candidate_binding_count"] == 12
    first = baseline["records"][0]

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append({
        "obligation_id": first["obligation_id"],
        "obligation_digest": first["obligation_digest"],
        "owner_id": "ACC-" + first["volume_key"],
        "severity": "high",
        "disposition": "evidence",
        "bound_at": "2026-09-30T17:15:00Z",
        "review_at": "2026-10-30T17:15:00Z",
        "evidence": [{
            "source": "test:existing-risk-control",
            "digest": "b" * 64,
            "category": "risk_control_evidence",
        }],
        "accepted_risk": None,
    })
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    before = registry_path.read_bytes()
    report = build_risk_classification_evidence(root, expected_head=HEAD)
    after = registry_path.read_bytes()

    assert before == after
    assert report["already_bound_count"] == 1
    assert report["candidate_binding_count"] == 11


def test_duplicate_governed_binding_identity_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append(dict(registry["records"][0]))
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="duplicate governed binding identity",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_report_is_deterministic_for_same_exact_head() -> None:
    left = build_risk_classification_evidence(ROOT, expected_head=HEAD)
    right = build_risk_classification_evidence(ROOT, expected_head=HEAD)
    assert left == right
    assert left["report_digest"] == right["report_digest"]
