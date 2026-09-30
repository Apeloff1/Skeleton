from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.build_p1_learning_eval_gap_evidence import (
    COVERAGE,
    LearningEvalGapEvidenceError,
    build_learning_eval_gap_evidence,
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

EXPECTED_GAPS = {
    ("VOL-077", "define experiment schema"),
    ("VOL-077", "bind experiments to reproducibility/provenance"),
    ("VOL-082", "define canonical benchmark registry"),
    ("VOL-082", "bind benchmark claims to reproducibility records"),
    ("VOL-324", "seed historical failure cases"),
    ("VOL-324", "bind promotion gates"),
    ("VOL-414", "define eligibility/redaction"),
    ("VOL-414", "bind champion/challenger"),
    ("VOL-415", "unify self-improvement registry"),
    ("VOL-415", "bind release gates"),
    ("VOL-419", "ingest incidents/negative results"),
    ("VOL-419", "bind risk/test generation"),
}


def _copy(root: Path, relative: Path) -> None:
    source = ROOT / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    required = {
        MASTER,
        P1_MAP,
        ADVERSARIAL,
        POLICY,
        REGISTRY,
    }
    for spec in COVERAGE.values():
        required.update(Path(item) for item in spec["sources"])
        required.update(Path(item) for item in spec["tests"])
    for relative in sorted(required, key=str):
        _copy(root, relative)
    return root


def _master_gaps(root: Path) -> set[tuple[str, str]]:
    payload = json.loads((root / MASTER).read_text(encoding="utf-8"))
    return {
        (str(volume["key"]), str(gap))
        for volume in payload["volumes"]
        if isinstance(volume, dict)
        for gap in volume.get("gaps", [])
    }


def test_live_learning_eval_batch_is_bounded_and_non_authoritative() -> None:
    report = build_learning_eval_gap_evidence(ROOT, expected_head=HEAD)

    assert set(COVERAGE) == EXPECTED_GAPS
    assert report["engine"] == "p1-learning-eval-gap-evidence-batch3-v1"
    assert report["batch_id"] == "p1-learning-eval-gap-batch3"
    assert report["category"] == "learning_eval_gap_closure"
    assert report["expected_head"] == HEAD
    assert report["covered_gap_count"] == 12
    assert report["covered_volume_count"] == 6
    assert report["already_bound_count"] == 12
    assert report["candidate_binding_count"] == 0
    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["clears_masterplan_gaps"] is False
    assert report["signs_accountability"] is False
    assert report["promotes_maturity"] is False
    assert len(report["report_digest"]) == 64

    rows = report["records"]
    assert len(rows) == 12
    assert len({row["obligation_id"] for row in rows}) == 12
    assert {
        (row["volume_key"], row["statement"])
        for row in rows
    } == EXPECTED_GAPS
    assert all(row["binding_present"] is True for row in rows)
    assert all(row["non_authoritative"] is True for row in rows)
    assert all(row["creates_binding"] is False for row in rows)
    assert all(row["clears_masterplan_gap"] is False for row in rows)
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
        == "learning_eval_gap_closure"
        for row in rows
    )


def test_live_masterplan_gap_strings_remain_canonical_and_present() -> None:
    before = _master_gaps(ROOT)
    report = build_learning_eval_gap_evidence(ROOT, expected_head=HEAD)
    after = _master_gaps(ROOT)

    assert EXPECTED_GAPS <= before
    assert after == before
    assert {
        (row["volume_key"], row["statement"])
        for row in report["records"]
    } == EXPECTED_GAPS


def test_live_registry_is_not_mutated_by_candidate_build() -> None:
    before = (ROOT / REGISTRY).read_bytes()
    report = build_learning_eval_gap_evidence(ROOT, expected_head=HEAD)
    after = (ROOT / REGISTRY).read_bytes()

    assert before == after
    assert report["creates_bindings"] is False
    assert report["already_bound_count"] == 12
    assert report["candidate_binding_count"] == 0


@pytest.mark.parametrize(
    "head",
    [
        "",
        "a" * 39,
        "A" * 40,
        "g" * 40,
        "a" * 41,
    ],
)
def test_invalid_exact_head_is_rejected(head: str) -> None:
    with pytest.raises(
        LearningEvalGapEvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_learning_eval_gap_evidence(ROOT, expected_head=head)


def test_missing_evidence_path_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    target = root / "skeleton/eval/shadow_traffic.py"
    target.unlink()

    with pytest.raises(
        LearningEvalGapEvidenceError,
        match="evidence path is missing",
    ):
        build_learning_eval_gap_evidence(root, expected_head=HEAD)


def test_missing_contract_marker_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    target = root / "skeleton/eval/experiment_registry.py"
    text = target.read_text(encoding="utf-8")
    assert "EXPERIMENT_SCHEMA_VERSION = 1" in text
    target.write_text(
        text.replace(
            "EXPERIMENT_SCHEMA_VERSION = 1",
            "EXPERIMENT_SCHEMA_VERSION = 2",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        LearningEvalGapEvidenceError,
        match="missing contract markers",
    ):
        build_learning_eval_gap_evidence(root, expected_head=HEAD)


def test_canonical_gap_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"] = [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] != "learning_eval_gap_closure"
    ]
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    master_path = root / MASTER
    master = json.loads(master_path.read_text(encoding="utf-8"))
    target = next(
        volume
        for volume in master["volumes"]
        if volume.get("key") == "VOL-077"
    )
    target["gaps"].remove("define experiment schema")
    master_path.write_text(
        json.dumps(master, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        LearningEvalGapEvidenceError,
        match="missing canonical gap obligation",
    ):
        build_learning_eval_gap_evidence(root, expected_head=HEAD)


def test_existing_binding_is_detected_but_not_rewritten(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"] = [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] != "learning_eval_gap_closure"
    ]
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    baseline = build_learning_eval_gap_evidence(root, expected_head=HEAD)
    assert baseline["already_bound_count"] == 0
    assert baseline["candidate_binding_count"] == 12
    first = baseline["records"][0]

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append(
        {
            "obligation_id": first["obligation_id"],
            "obligation_digest": first["obligation_digest"],
            "owner_id": "ACC-" + first["volume_key"],
            "severity": "high",
            "disposition": "evidence",
            "bound_at": "2026-09-30T16:00:00Z",
            "review_at": "2026-10-30T16:00:00Z",
            "evidence": [
                {
                    "source": "test:preexisting-learning-binding",
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
    report = build_learning_eval_gap_evidence(root, expected_head=HEAD)
    after = registry_path.read_bytes()

    assert before == after
    assert report["already_bound_count"] == 1
    assert report["candidate_binding_count"] == 11
    row = next(
        row
        for row in report["records"]
        if row["obligation_id"] == first["obligation_id"]
    )
    assert row["binding_present"] is True


def test_report_is_deterministic_for_same_head() -> None:
    left = build_learning_eval_gap_evidence(ROOT, expected_head=HEAD)
    right = build_learning_eval_gap_evidence(ROOT, expected_head=HEAD)

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
        LearningEvalGapEvidenceError,
        match="risk registry record .* must be an object",
    ):
        build_learning_eval_gap_evidence(root, expected_head=HEAD)


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
        LearningEvalGapEvidenceError,
        match="duplicate governed binding identity",
    ):
        build_learning_eval_gap_evidence(root, expected_head=HEAD)


def test_unknown_governed_binding_identity_fails_closed(
    tmp_path: Path,
) -> None:
    root = _copy_repo(tmp_path)
    registry_path = root / REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["records"].append(
        {
            "obligation_id": (
                "P1-GAP-UNKNOWN:gap:deadbeef-deadbeefdeadbeef"
            ),
        }
    )
    registry_path.write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        LearningEvalGapEvidenceError,
        match="risk registry references unknown obligations",
    ):
        build_learning_eval_gap_evidence(root, expected_head=HEAD)
