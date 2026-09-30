from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil

import pytest

from scripts.reconcile_p1_risk_evidence import (
    ADVERSARIAL,
    CLOSURE,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    RiskReconciliationError,
    derive_obligations,
    reconcile_repository,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _copy_file(root: Path, relative: Path) -> None:
    source = ROOT / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        MASTER,
        P1_MAP,
        ADVERSARIAL,
        CLOSURE,
        POLICY,
        REGISTRY,
        Path("skeleton/contracts/risk_evidence.py"),
        Path("scripts/reconcile_p1_risk_evidence.py"),
    ):
        _copy_file(root, relative)
    return root


def _load(root: Path, relative: Path) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write(root: Path, relative: Path, payload: dict) -> None:
    (root / relative).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _first_obligation(root: Path):
    obligations = derive_obligations(
        _load(root, MASTER),
        _load(root, P1_MAP),
        _load(root, ADVERSARIAL),
        _load(root, POLICY),
    )
    return next(item for item in obligations if item.kind.value == "risk")


def _evidence_record(obligation, *, owner: str = "owner:test") -> dict:
    return {
        "obligation_id": obligation.obligation_id,
        "obligation_digest": obligation.obligation_digest,
        "owner_id": owner,
        "severity": "high",
        "disposition": "evidence",
        "bound_at": "2026-09-27T19:00:00Z",
        "review_at": "2026-10-27T19:00:00Z",
        "evidence": [
            {
                "source": "tests/test_p1_risk_evidence_reconciliation.py",
                "digest": "1" * 64,
                "category": "test",
            }
        ],
        "accepted_risk": None,
    }


def test_live_p1_risk_inventory_is_deterministic_and_non_authoritative() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["inventory"] == {
        "p1_primary_volume_count": 107,
        "volume_risk_count": 281,
        "volume_gap_count": 208,
        "applicable_adversarial_axis_count": 24,
        "total_obligation_count": 513,
    }
    assert report["binding_count"] == 493
    assert report["resolved_count"] == 493
    assert report["unresolved_blocking_count"] == 20
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 493,
        "unbound": 20,
    }
    assert report["non_authoritative"] is True
    assert report["source_mutation_detected"] is False
    assert len(report["report_digest"]) == 64


def test_reconciliation_is_deterministic_for_same_evaluation_time() -> None:
    left = reconcile_repository(ROOT, evaluated_at=NOW)
    right = reconcile_repository(ROOT, evaluated_at=NOW)

    assert left == right
    assert left["report_digest"] == right["report_digest"]


def test_reconciliation_never_mutates_canonical_sources(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    tracked = (
        MASTER,
        P1_MAP,
        ADVERSARIAL,
        CLOSURE,
        POLICY,
        REGISTRY,
        Path("skeleton/contracts/risk_evidence.py"),
        Path("scripts/reconcile_p1_risk_evidence.py"),
    )
    before = {
        path: (root / path).read_bytes()
        for path in tracked
    }

    report = reconcile_repository(root, evaluated_at=NOW)

    assert report["source_mutation_detected"] is False
    assert {
        path: (root / path).read_bytes()
        for path in tracked
    } == before


@pytest.mark.parametrize(
    ("field", "delta"),
    (
        ("p1_primary_volume_count", 1),
        ("volume_risk_count", 1),
        ("volume_gap_count", -1),
        ("applicable_adversarial_axis_count", 1),
        ("total_obligation_count", -1),
    ),
)
def test_inventory_drift_fails_closed(
    tmp_path: Path,
    field: str,
    delta: int,
) -> None:
    root = _copy_tree(tmp_path)
    policy = _load(root, POLICY)
    policy["inventory_expectations"][field] += delta
    _write(root, POLICY, policy)

    with pytest.raises(
        RiskReconciliationError,
        match="risk obligation inventory drift",
    ):
        reconcile_repository(root, evaluated_at=NOW)


def test_unknown_binding_identity_fails_closed(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    registry = _load(root, REGISTRY)
    record = _evidence_record(_first_obligation(root))
    record["obligation_id"] = "P1-RISK-UNKNOWN-deadbeefdeadbeef"
    registry["records"] = [record]
    _write(root, REGISTRY, registry)

    with pytest.raises(
        RiskReconciliationError,
        match="bindings reference unknown obligations",
    ):
        reconcile_repository(root, evaluated_at=NOW)


def test_duplicate_binding_fails_closed(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    registry = _load(root, REGISTRY)
    record = _evidence_record(_first_obligation(root))
    registry["records"] = [record, json.loads(json.dumps(record))]
    _write(root, REGISTRY, registry)

    with pytest.raises(
        RiskReconciliationError,
        match="duplicate risk binding",
    ):
        reconcile_repository(root, evaluated_at=NOW)


def test_binding_digest_mismatch_remains_unresolved(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    obligation = _first_obligation(root)
    registry = _load(root, REGISTRY)
    record = _evidence_record(obligation)
    record["obligation_digest"] = "f" * 64
    registry["records"] = [record]
    _write(root, REGISTRY, registry)

    report = reconcile_repository(root, evaluated_at=NOW)
    row = next(
        row
        for row in report["records"]
        if row["obligation"]["obligation_id"] == obligation.obligation_id
    )

    assert row["evaluation"]["resolved"] is False
    assert "binding obligation_digest mismatch" in row["evaluation"]["blockers"]


def test_one_real_binding_changes_only_its_own_resolution(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    obligation = _first_obligation(root)
    registry = _load(root, REGISTRY)
    registry["records"] = [_evidence_record(obligation)]
    _write(root, REGISTRY, registry)

    report = reconcile_repository(root, evaluated_at=NOW)

    assert report["binding_count"] == 1
    assert report["resolved_count"] == 1
    assert report["unresolved_blocking_count"] == 512
    assert report["unclassified_count"] == 280


def test_stale_binding_review_remains_unresolved(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    obligation = _first_obligation(root)
    registry = _load(root, REGISTRY)
    record = _evidence_record(obligation)
    record["review_at"] = "2026-09-27T20:00:00Z"
    registry["records"] = [record]
    _write(root, REGISTRY, registry)

    report = reconcile_repository(
        root,
        evaluated_at=NOW + timedelta(hours=1),
    )
    row = next(
        row
        for row in report["records"]
        if row["obligation"]["obligation_id"] == obligation.obligation_id
    )

    assert row["evaluation"]["resolved"] is False
    assert "binding review is overdue" in row["evaluation"]["blockers"]


def test_masterplan_authority_pointer_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    master = _load(root, MASTER)
    master["authority"]["p1_risk_evidence_registry"] = "machine/wrong.json"
    _write(root, MASTER, master)

    with pytest.raises(
        RiskReconciliationError,
        match="authority pointer drift",
    ):
        reconcile_repository(root, evaluated_at=NOW)


def test_empty_baseline_closure_evidence_fails_closed(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    closure = _load(root, CLOSURE)
    closure["entries"] = []
    _write(root, CLOSURE, closure)

    with pytest.raises(
        RiskReconciliationError,
        match="baseline closure evidence entries must be non-empty",
    ):
        reconcile_repository(root, evaluated_at=NOW)

def test_policy_rejects_accepted_risk_signer_type_drift(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    policy = _load(root, POLICY)
    policy["binding_rules"]["accepted_risk_signer_types"] = [
        "human",
        "governance",
    ]
    _write(root, POLICY, policy)

    with pytest.raises(
        RiskReconciliationError,
        match="accepted-risk signer type policy drift",
    ):
        reconcile_repository(root, evaluated_at=NOW)


def test_policy_rejects_accepted_risk_signature_method_drift(
    tmp_path: Path,
) -> None:
    root = _copy_tree(tmp_path)
    policy = _load(root, POLICY)
    policy["binding_rules"]["accepted_risk_signature_methods"].append(
        "contract_attestation"
    )
    _write(root, POLICY, policy)

    with pytest.raises(
        RiskReconciliationError,
        match="accepted-risk signature method policy drift",
    ):
        reconcile_repository(root, evaluated_at=NOW)
