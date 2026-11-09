from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_regression_corpus import (
    RegressionCorpusValidationError,
    compare_corpora,
    validate_repository,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/p1_regression_corpus.json")


def _payload() -> dict:
    return json.loads((ROOT / REGISTRY).read_text(encoding="utf-8"))


def _write(root: Path, payload: dict, name: str) -> Path:
    path = Path(name)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_repository_corpus_is_valid_and_seeded() -> None:
    report = validate_repository(ROOT)

    assert report["valid"] is True
    assert report["task_id"] == "P1-LEARN-05"
    assert report["accountability_ref"] == "ACC-P1-LEARN-05"
    assert report["case_count"] >= 4
    assert report["production_authority"] is False
    assert {
        "specification_gaming",
        "reasoning_error",
        "evidence_substitution",
        "side_effect_escape",
    }.issubset(report["failure_classes"])


def test_policy_drift_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["policy"]["all_cases_promotion_blocking"] = False
    path = _write(
        tmp_path,
        payload,
        "machine/p1_regression_corpus.json",
    )

    with pytest.raises(
        RegressionCorpusValidationError,
        match="regression policy drift",
    ):
        validate_repository(tmp_path, registry_path=path)


def test_existing_case_cannot_mutate(tmp_path: Path) -> None:
    baseline = _payload()
    candidate = json.loads(json.dumps(baseline))
    candidate["cases"][0]["expected_outcome"] = "safe_complete"

    baseline_path = _write(
        tmp_path,
        baseline,
        "machine/baseline.json",
    )
    candidate_path = _write(
        tmp_path,
        candidate,
        "machine/candidate.json",
    )
    report = compare_corpora(
        tmp_path,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )

    assert report["accepted"] is False
    assert report["mutated"] == [["spec-game-001", 1]]


def test_existing_case_cannot_be_removed(tmp_path: Path) -> None:
    baseline = _payload()
    candidate = json.loads(json.dumps(baseline))
    candidate["cases"] = candidate["cases"][1:]

    baseline_path = _write(
        tmp_path,
        baseline,
        "machine/baseline.json",
    )
    candidate_path = _write(
        tmp_path,
        candidate,
        "machine/candidate.json",
    )

    with pytest.raises(
        RegressionCorpusValidationError,
        match="required failure classes missing",
    ):
        compare_corpora(
            tmp_path,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
        )


def test_case_risk_must_be_promotion_blocking(tmp_path: Path) -> None:
    payload = _payload()
    payload["cases"][0]["risk"]["blocking_by_default"] = False
    path = _write(
        tmp_path,
        payload,
        "machine/p1_regression_corpus.json",
    )

    with pytest.raises(
        RegressionCorpusValidationError,
        match="risk must be blocking",
    ):
        validate_repository(tmp_path, registry_path=path)


def test_case_risk_requires_regression_evidence_mode(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["cases"][0]["risk"]["required_evidence_modes"] = [
        "adversarial"
    ]
    path = _write(
        tmp_path,
        payload,
        "machine/p1_regression_corpus.json",
    )

    with pytest.raises(
        RegressionCorpusValidationError,
        match="requires regression evidence",
    ):
        validate_repository(tmp_path, registry_path=path)


def test_unknown_fields_fail_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["cases"][0]["silent_override"] = True
    path = _write(
        tmp_path,
        payload,
        "machine/p1_regression_corpus.json",
    )

    with pytest.raises(
        RegressionCorpusValidationError,
        match="unknown fields",
    ):
        validate_repository(tmp_path, registry_path=path)
