from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.build_p1_risk_classification_evidence import (
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
    ("VOL-056", "orphan gaps"),
    ("VOL-056", "status inflation"),
    ("VOL-056", "duplicate/conflicting records"),
    ("VOL-057", "critical risk hidden by aggregate status"),
    ("VOL-057", "paper control without evidence"),
    ("VOL-059", "false green aggregation"),
    ("VOL-059", "non-reproducible failure"),
    ("VOL-078", "hidden dependency"),
    ("VOL-078", "false deterministic claim"),
    ("VOL-420", "breadth inflation"),
    ("VOL-420", "misfit requirement forced into wrong volume"),
    ("VOL-077", "production contamination"),
    ("VOL-082", "benchmark leakage"),
    ("VOL-082", "cherry-picked baselines"),
    ("VOL-414", "candidate side effect leaks"),
    ("VOL-414", "non-comparable traffic"),
    ("VOL-415", "benchmark gaming"),
    ("VOL-415", "candidate overwrites champion"),
    ("VOL-419", "same failure repeated"),
    ("VOL-419", "anecdote becomes dogma"),
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


def _master_risks(root: Path) -> set[tuple[str, str]]:
    payload = json.loads((root / MASTER).read_text(encoding="utf-8"))
    return {
        (str(volume["key"]), str(risk))
        for volume in payload["volumes"]
        if isinstance(volume, dict)
        for risk in volume.get("risks", [])
    }


def test_live_batch4_is_bounded_high_severity_and_non_authoritative() -> None:
    report = build_risk_classification_evidence(ROOT, expected_head=HEAD)

    assert set(COVERAGE) == EXPECTED_RISKS
    assert report["engine"] == "p1-risk-classification-evidence-batch4-v1"
    assert report["batch_id"] == "p1-risk-classification-batch4"
    assert report["category"] == "risk_classification_evidence"
    assert report["expected_head"] == HEAD
    assert report["covered_risk_count"] == 20
    assert report["covered_volume_count"] == 11
    assert report["proposed_severity"] == "high"
    assert report["already_bound_count"] == 0
    assert report["candidate_binding_count"] == 20
    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["signs_accountability"] is False
    assert report["promotes_maturity"] is False
    assert len(report["report_digest"]) == 64

    rows = report["records"]
    assert len(rows) == 20
    assert len({row["obligation_id"] for row in rows}) == 20
    assert {
        (row["volume_key"], row["statement"])
        for row in rows
    } == EXPECTED_RISKS
    assert all(row["proposed_severity"] == "high" for row in rows)
    assert all(row["proposed_disposition"] == "evidence" for row in rows)
    assert all(row["binding_present"] is False for row in rows)
    assert all(row["non_authoritative"] is True for row in rows)
    assert all(row["creates_binding"] is False for row in rows)
    assert all(row["accepts_risk"] is False for row in rows)
    assert all(row["signs_accountability"] is False for row in rows)
    assert all(row["promotes_maturity"] is False for row in rows)
    assert all(len(row["packet_digest"]) == 64 for row in rows)
    assert all(
        row["candidate_evidence_ref"]["source"].endswith(":" + HEAD)
        for row in rows
    )
    assert all(
        row["candidate_evidence_ref"]["digest"] == row["packet_digest"]
        for row in rows
    )
    assert all(
        row["candidate_evidence_ref"]["category"]
        == "risk_classification_evidence"
        for row in rows
    )


def test_live_masterplan_risk_strings_remain_canonical_and_present() -> None:
    before = _master_risks(ROOT)
    report = build_risk_classification_evidence(ROOT, expected_head=HEAD)
    after = _master_risks(ROOT)

    assert EXPECTED_RISKS <= before
    assert after == before
    assert {
        (row["volume_key"], row["statement"])
        for row in report["records"]
    } == EXPECTED_RISKS


def test_candidate_build_does_not_mutate_governed_registry() -> None:
    before = (ROOT / REGISTRY).read_bytes()
    report = build_risk_classification_evidence(ROOT, expected_head=HEAD)
    after = (ROOT / REGISTRY).read_bytes()

    assert before == after
    assert report["already_bound_count"] == 0
    assert report["candidate_binding_count"] == 20
    assert report["creates_bindings"] is False


@pytest.mark.parametrize(
    "head",
    ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41],
)
def test_invalid_exact_head_is_rejected(head: str) -> None:
    with pytest.raises(
        RiskClassificationEvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_risk_classification_evidence(ROOT, expected_head=head)


def test_missing_evidence_path_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    target = root / "skeleton/eval/shadow_traffic.py"
    target.unlink()

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="evidence path is missing",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_missing_contract_marker_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    target = root / "skeleton/contracts/risk_evidence.py"
    text = target.read_text(encoding="utf-8")
    assert "evidence disposition requires evidence" in text
    target.write_text(
        text.replace(
            "evidence disposition requires evidence",
            "changed evidence rule",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="missing contract markers",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_canonical_risk_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    master_path = root / MASTER
    master = json.loads(master_path.read_text(encoding="utf-8"))
    target = next(
        row for row in master["volumes"] if row.get("key") == "VOL-056"
    )
    target["risks"].remove("orphan gaps")
    master_path.write_text(
        json.dumps(master, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="missing canonical risk obligation",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_existing_binding_is_detected_without_rewrite(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    baseline = build_risk_classification_evidence(root, expected_head=HEAD)
    first = baseline["records"][0]

    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append(
        {
            "obligation_id": first["obligation_id"],
            "obligation_digest": first["obligation_digest"],
            "owner_id": "ACC-" + first["volume_key"],
            "severity": "high",
            "disposition": "evidence",
            "bound_at": "2026-09-30T17:00:00Z",
            "review_at": "2026-10-30T17:00:00Z",
            "evidence": [
                {
                    "source": "test:preexisting-risk-classification",
                    "digest": "b" * 64,
                    "category": "test",
                }
            ],
            "accepted_risk": None,
        }
    )
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    before = registry_path.read_bytes()
    report = build_risk_classification_evidence(root, expected_head=HEAD)
    after = registry_path.read_bytes()

    assert before == after
    assert report["already_bound_count"] == 1
    assert report["candidate_binding_count"] == 19


def test_report_is_deterministic_for_same_head() -> None:
    left = build_risk_classification_evidence(ROOT, expected_head=HEAD)
    right = build_risk_classification_evidence(ROOT, expected_head=HEAD)

    assert left == right
    assert left["report_digest"] == right["report_digest"]


def test_malformed_registry_row_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append("not-an-object")
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="risk registry record .* must be an object",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_duplicate_governed_binding_identity_fails_closed(
    tmp_path: Path,
) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["records"]
    registry["records"].append(dict(registry["records"][0]))
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="duplicate governed binding identity",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)


def test_unknown_governed_binding_identity_fails_closed(
    tmp_path: Path,
) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append(
        {"obligation_id": "P1-RISK-UNKNOWN:risk:deadbeef-deadbeefdeadbeef"}
    )
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RiskClassificationEvidenceError,
        match="risk registry references unknown obligations",
    ):
        build_risk_classification_evidence(root, expected_head=HEAD)
