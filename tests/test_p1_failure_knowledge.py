from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_failure_knowledge import (
    FailureKnowledgeValidationError,
    compare_ledgers,
    validate_repository,
)


ROOT = Path(__file__).resolve().parents[1]
LEDGER = Path("machine/p1_failure_knowledge.json")
REGRESSIONS = Path("machine/p1_regression_corpus.json")


def _payload() -> dict:
    return json.loads((ROOT / LEDGER).read_text(encoding="utf-8"))


def _write(root: Path, payload: dict, name: str) -> Path:
    path = Path(name)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _copy_regressions(root: Path) -> None:
    target = root / REGRESSIONS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT / REGRESSIONS).read_bytes())


def test_repository_failure_knowledge_is_valid() -> None:
    report = validate_repository(ROOT)

    assert report["valid"] is True
    assert report["task_id"] == "P1-LEARN-06"
    assert report["accountability_ref"] == "ACC-P1-LEARN-06"
    assert report["record_count"] >= 4
    assert report["production_authority"] is False
    assert report["direct_self_modify"] is False
    assert {
        "incident",
        "failed_experiment",
        "rejected_design",
        "counterexample",
    }.issubset(report["source_kinds"])


def test_policy_drift_fails_closed(tmp_path: Path) -> None:
    _copy_regressions(tmp_path)
    payload = _payload()
    payload["policy"]["direct_self_modify"] = True
    path = _write(
        tmp_path,
        payload,
        "machine/p1_failure_knowledge.json",
    )

    with pytest.raises(
        FailureKnowledgeValidationError,
        match="policy drift",
    ):
        validate_repository(tmp_path, ledger_path=path)


def test_unknown_regression_case_fails_closed(tmp_path: Path) -> None:
    _copy_regressions(tmp_path)
    payload = _payload()
    payload["records"][0]["regression_case_id"] = "unknown-case"
    path = _write(
        tmp_path,
        payload,
        "machine/p1_failure_knowledge.json",
    )

    with pytest.raises(
        FailureKnowledgeValidationError,
        match="unknown regression case",
    ):
        validate_repository(tmp_path, ledger_path=path)


def test_existing_record_cannot_mutate(tmp_path: Path) -> None:
    _copy_regressions(tmp_path)
    baseline = _payload()
    candidate = json.loads(json.dumps(baseline))
    candidate["records"][0]["summary"] = (
        "Mutated historical interpretation."
    )
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

    report = compare_ledgers(
        tmp_path,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )

    assert report["accepted"] is False
    assert report["mutated"] == [["failure-spec-game-001", 1]]


def test_existing_record_cannot_be_removed(tmp_path: Path) -> None:
    _copy_regressions(tmp_path)
    baseline = _payload()
    candidate = json.loads(json.dumps(baseline))
    candidate["records"] = candidate["records"][1:]
    for index, record in enumerate(candidate["records"], start=1):
        record["sequence"] = index
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
        FailureKnowledgeValidationError,
        match="required source kinds missing",
    ):
        compare_ledgers(
            tmp_path,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
        )


def test_unknown_fields_fail_closed(tmp_path: Path) -> None:
    _copy_regressions(tmp_path)
    payload = _payload()
    payload["records"][0]["self_modify"] = True
    path = _write(
        tmp_path,
        payload,
        "machine/p1_failure_knowledge.json",
    )

    with pytest.raises(
        FailureKnowledgeValidationError,
        match="unknown fields",
    ):
        validate_repository(tmp_path, ledger_path=path)
