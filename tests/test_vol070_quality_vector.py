from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skeleton/eval/quality_vector.py"
MIRROR_PATH = ROOT / "skeleton/ai/evaluation/quality_vector.py"
SPEC = importlib.util.spec_from_file_location("vol070_quality_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

QualityContractError = MODULE.QualityContractError
QualityDimensionPolicy = MODULE.QualityDimensionPolicy
QualityDirection = MODULE.QualityDirection
QualityMeasurement = MODULE.QualityMeasurement
QualityPolicy = MODULE.QualityPolicy

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
MANIFEST = ROOT / "machine/ai_quality_vector.json"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def policy() -> QualityPolicy:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dimensions = []
    for item in payload["dimensions"]:
        row = dict(item)
        row["direction"] = QualityDirection(row["direction"])
        dimensions.append(QualityDimensionPolicy(**row))
    return QualityPolicy(
        dimensions,
        minimum_aggregate_score=payload["minimum_aggregate_score"],
        max_future_skew_seconds=payload["max_future_skew_seconds"],
    )


def measurement(
    dimension_id: str,
    raw_value: float,
    *,
    uncertainty: float,
    unit: str,
    owner: str,
    suite: str,
    measured_at: datetime = NOW - timedelta(minutes=5),
) -> QualityMeasurement:
    return QualityMeasurement(
        measurement_id=f"m-{dimension_id}",
        dimension_id=dimension_id,
        raw_value=raw_value,
        uncertainty=uncertainty,
        unit=unit,
        measured_at=measured_at.isoformat(),
        evaluation_owner_id=owner,
        evaluation_suite_id=suite,
        evidence_digest=digest(dimension_id),
    )


def passing_measurements() -> tuple[QualityMeasurement, ...]:
    return (
        measurement(
            "correctness",
            0.97,
            uncertainty=0.01,
            unit="score",
            owner="eval-correctness",
            suite="correctness-v1",
        ),
        measurement(
            "groundedness",
            0.96,
            uncertainty=0.01,
            unit="score",
            owner="eval-groundedness",
            suite="groundedness-v1",
        ),
        measurement(
            "safety-risk",
            0.005,
            uncertainty=0.005,
            unit="probability",
            owner="eval-safety",
            suite="safety-risk-v1",
        ),
        measurement(
            "robustness",
            0.9,
            uncertainty=0.02,
            unit="score",
            owner="eval-robustness",
            suite="robustness-v1",
        ),
        measurement(
            "latency",
            500.0,
            uncertainty=50.0,
            unit="milliseconds",
            owner="eval-performance",
            suite="latency-v1",
        ),
        measurement(
            "cost",
            0.02,
            uncertainty=0.005,
            unit="usd",
            owner="eval-efficiency",
            suite="cost-v1",
        ),
    )


def replace_measurement(
    items: tuple[QualityMeasurement, ...],
    dimension_id: str,
    replacement: QualityMeasurement,
) -> tuple[QualityMeasurement, ...]:
    return tuple(
        replacement if item.dimension_id == dimension_id else item
        for item in items
    )


def result(vector, dimension_id: str):
    return next(
        item for item in vector.dimensions if item.dimension_id == dimension_id
    )


def test_manifest_binds_all_dimensions_to_eval_suites() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["volume"] == "VOL-070"
    assert payload["status"] == "implementation_contract"
    assert len(payload["dimensions"]) == 6
    for dimension in payload["dimensions"]:
        assert dimension["evaluation_owner_id"]
        assert dimension["evaluation_suite_id"]
        assert "hard_failure" in dimension


def test_full_passing_vector_is_promotion_eligible() -> None:
    vector = policy().evaluate(passing_measurements(), now=NOW)
    assert vector.promotion_eligible is True
    assert vector.hard_failures == ()
    assert vector.aggregate_score >= vector.minimum_aggregate_score
    policy().verify(vector)


def test_raw_measurement_and_uncertainty_remain_visible() -> None:
    vector = policy().evaluate(passing_measurements(), now=NOW)
    correctness = result(vector, "correctness")
    assert correctness.raw_value == 0.97
    assert correctness.uncertainty == 0.01
    assert correctness.unit == "score"
    assert correctness.conservative_value == pytest.approx(0.96)


def test_higher_is_better_uses_lower_uncertainty_bound() -> None:
    items = passing_measurements()
    borderline = measurement(
        "correctness",
        0.91,
        uncertainty=0.02,
        unit="score",
        owner="eval-correctness",
        suite="correctness-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "correctness", borderline),
        now=NOW,
    )
    correctness = result(vector, "correctness")
    assert correctness.conservative_value == pytest.approx(0.89)
    assert "threshold-failure" in correctness.reasons
    assert "correctness" in vector.hard_failures


def test_lower_is_better_uses_upper_uncertainty_bound() -> None:
    items = passing_measurements()
    borderline = measurement(
        "safety-risk",
        0.015,
        uncertainty=0.01,
        unit="probability",
        owner="eval-safety",
        suite="safety-risk-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "safety-risk", borderline),
        now=NOW,
    )
    safety = result(vector, "safety-risk")
    assert safety.conservative_value == pytest.approx(0.025)
    assert "threshold-failure" in safety.reasons


def test_hard_failure_cannot_be_compensated_by_high_aggregate() -> None:
    items = passing_measurements()
    failed_safety = measurement(
        "safety-risk",
        0.03,
        uncertainty=0.0,
        unit="probability",
        owner="eval-safety",
        suite="safety-risk-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "safety-risk", failed_safety),
        now=NOW,
    )
    assert vector.aggregate_score >= 0.75
    assert vector.promotion_eligible is False
    assert vector.hard_failures == ("safety-risk",)


def test_soft_failure_can_be_compensated_only_by_aggregate_policy() -> None:
    items = passing_measurements()
    slow = measurement(
        "latency",
        2000.0,
        uncertainty=0.0,
        unit="milliseconds",
        owner="eval-performance",
        suite="latency-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "latency", slow),
        now=NOW,
    )
    assert result(vector, "latency").passed is False
    assert vector.hard_failures == ()
    assert vector.aggregate_score >= 0.75
    assert vector.promotion_eligible is True


def test_missing_hard_dimension_is_non_compensable() -> None:
    items = tuple(
        item
        for item in passing_measurements()
        if item.dimension_id != "groundedness"
    )
    vector = policy().evaluate(items, now=NOW)
    groundedness = result(vector, "groundedness")
    assert groundedness.raw_value is None
    assert groundedness.reasons == ("missing-measurement",)
    assert "groundedness" in vector.hard_failures
    assert vector.promotion_eligible is False


def test_wrong_suite_fails_dimension() -> None:
    items = passing_measurements()
    wrong = measurement(
        "correctness",
        1.0,
        uncertainty=0.0,
        unit="score",
        owner="eval-correctness",
        suite="wrong-suite",
    )
    vector = policy().evaluate(
        replace_measurement(items, "correctness", wrong),
        now=NOW,
    )
    assert "evaluation-suite-mismatch" in result(
        vector, "correctness"
    ).reasons
    assert vector.promotion_eligible is False


def test_wrong_owner_fails_dimension() -> None:
    items = passing_measurements()
    wrong = measurement(
        "groundedness",
        1.0,
        uncertainty=0.0,
        unit="score",
        owner="eval-correctness",
        suite="groundedness-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "groundedness", wrong),
        now=NOW,
    )
    assert "evaluation-owner-mismatch" in result(
        vector, "groundedness"
    ).reasons


def test_unit_mismatch_fails_dimension() -> None:
    items = passing_measurements()
    wrong = measurement(
        "latency",
        0.5,
        uncertainty=0.0,
        unit="seconds",
        owner="eval-performance",
        suite="latency-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "latency", wrong),
        now=NOW,
    )
    assert "unit-mismatch" in result(vector, "latency").reasons


def test_uncertainty_limit_is_enforced_separately_from_threshold() -> None:
    items = passing_measurements()
    uncertain = measurement(
        "correctness",
        1.0,
        uncertainty=0.04,
        unit="score",
        owner="eval-correctness",
        suite="correctness-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "correctness", uncertain),
        now=NOW,
    )
    assert "uncertainty-above-limit" in result(
        vector, "correctness"
    ).reasons


def test_stale_measurement_fails_closed() -> None:
    items = passing_measurements()
    stale = measurement(
        "correctness",
        1.0,
        uncertainty=0.0,
        unit="score",
        owner="eval-correctness",
        suite="correctness-v1",
        measured_at=NOW - timedelta(days=2),
    )
    vector = policy().evaluate(
        replace_measurement(items, "correctness", stale),
        now=NOW,
    )
    assert "stale-measurement" in result(vector, "correctness").reasons


def test_future_measurement_beyond_skew_fails_closed() -> None:
    items = passing_measurements()
    future = measurement(
        "correctness",
        1.0,
        uncertainty=0.0,
        unit="score",
        owner="eval-correctness",
        suite="correctness-v1",
        measured_at=NOW + timedelta(seconds=6),
    )
    vector = policy().evaluate(
        replace_measurement(items, "correctness", future),
        now=NOW,
    )
    assert "measurement-from-future" in result(
        vector, "correctness"
    ).reasons


def test_duplicate_measurement_identity_fails_closed() -> None:
    items = passing_measurements()
    with pytest.raises(QualityContractError, match="duplicate measurement_id"):
        policy().evaluate(items + (items[0],), now=NOW)


def test_duplicate_dimension_measurement_fails_closed() -> None:
    items = passing_measurements()
    duplicate = QualityMeasurement(
        measurement_id="m-correctness-second",
        dimension_id="correctness",
        raw_value=0.99,
        uncertainty=0.0,
        unit="score",
        measured_at=NOW.isoformat(),
        evaluation_owner_id="eval-correctness",
        evaluation_suite_id="correctness-v1",
        evidence_digest=digest("second"),
    )
    with pytest.raises(QualityContractError, match="duplicate measurement for"):
        policy().evaluate(items + (duplicate,), now=NOW)


def test_unknown_dimension_measurement_fails_closed() -> None:
    unknown = QualityMeasurement(
        measurement_id="m-unknown",
        dimension_id="unknown",
        raw_value=1.0,
        uncertainty=0.0,
        unit="score",
        measured_at=NOW.isoformat(),
        evaluation_owner_id="eval-unknown",
        evaluation_suite_id="unknown-v1",
        evidence_digest=digest("unknown"),
    )
    with pytest.raises(QualityContractError, match="unknown dimension"):
        policy().evaluate(passing_measurements() + (unknown,), now=NOW)


def test_vector_is_deterministic_across_measurement_order() -> None:
    items = passing_measurements()
    first = policy().evaluate(items, now=NOW)
    second = policy().evaluate(tuple(reversed(items)), now=NOW)
    assert first.to_wire() == second.to_wire()


def test_vector_receipt_tampering_is_detected() -> None:
    vector = policy().evaluate(passing_measurements(), now=NOW)
    forged = replace(vector, receipt_digest="0" * 64)
    with pytest.raises(QualityContractError, match="integrity"):
        policy().verify(forged)


def test_unresealed_hard_failure_ledger_tampering_fails_at_receipt_integrity() -> None:
    items = passing_measurements()
    failed = measurement(
        "safety-risk",
        0.03,
        uncertainty=0.0,
        unit="probability",
        owner="eval-safety",
        suite="safety-risk-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "safety-risk", failed),
        now=NOW,
    )
    forged = replace(vector, hard_failures=())

    with pytest.raises(
        QualityContractError,
        match="quality-vector receipt failed integrity verification",
    ):
        policy().verify(forged)


def test_policy_drift_invalidates_vector() -> None:
    vector = policy().evaluate(passing_measurements(), now=NOW)
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dimensions = []
    for item in payload["dimensions"]:
        row = dict(item)
        row["direction"] = QualityDirection(row["direction"])
        dimensions.append(QualityDimensionPolicy(**row))
    changed = QualityPolicy(
        dimensions,
        minimum_aggregate_score=0.8,
        max_future_skew_seconds=5,
    )
    with pytest.raises(QualityContractError, match="policy digest drift"):
        changed.verify(vector)


def test_hard_failure_ledger_tampering_is_detected() -> None:
    items = passing_measurements()
    failed = measurement(
        "safety-risk",
        0.03,
        uncertainty=0.0,
        unit="probability",
        owner="eval-safety",
        suite="safety-risk-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "safety-risk", failed),
        now=NOW,
    )
    forged = replace(vector, hard_failures=())
    payload = forged.to_wire()
    payload.pop("receipt_digest")
    forged = replace(
        forged,
        receipt_digest=hashlib.sha256(
            json.dumps(
                {
                    "schema": MODULE.QUALITY_VECTOR_SCHEMA,
                    "kind": "quality-vector",
                    **payload,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
    )
    with pytest.raises(QualityContractError, match="hard-failure ledger"):
        policy().verify(forged)


def test_eligibility_tampering_is_detected() -> None:
    items = passing_measurements()
    failed = measurement(
        "safety-risk",
        0.03,
        uncertainty=0.0,
        unit="probability",
        owner="eval-safety",
        suite="safety-risk-v1",
    )
    vector = policy().evaluate(
        replace_measurement(items, "safety-risk", failed),
        now=NOW,
    )
    with pytest.raises(QualityContractError, match="hard failure"):
        replace(vector, promotion_eligible=True)


def test_nonfinite_measurement_fails_closed() -> None:
    with pytest.raises(QualityContractError, match="finite"):
        QualityMeasurement(
            measurement_id="bad",
            dimension_id="correctness",
            raw_value=float("nan"),
            uncertainty=0.0,
            unit="score",
            measured_at=NOW.isoformat(),
            evaluation_owner_id="eval-correctness",
            evaluation_suite_id="correctness-v1",
            evidence_digest=digest("bad"),
        )


def test_invalid_higher_policy_geometry_is_rejected() -> None:
    with pytest.raises(QualityContractError, match="higher-is-better"):
        QualityDimensionPolicy(
            dimension_id="bad",
            unit="score",
            direction=QualityDirection.HIGHER_IS_BETTER,
            threshold=0.9,
            quality_best=0.8,
            quality_worst=0.0,
            evaluation_owner_id="eval-bad",
            evaluation_suite_id="bad-v1",
            max_uncertainty=0.1,
            max_age_seconds=60,
            weight=1.0,
            hard_failure=True,
        )


def test_invalid_lower_policy_geometry_is_rejected() -> None:
    with pytest.raises(QualityContractError, match="lower-is-better"):
        QualityDimensionPolicy(
            dimension_id="bad",
            unit="score",
            direction=QualityDirection.LOWER_IS_BETTER,
            threshold=0.1,
            quality_best=0.2,
            quality_worst=1.0,
            evaluation_owner_id="eval-bad",
            evaluation_suite_id="bad-v1",
            max_uncertainty=0.1,
            max_age_seconds=60,
            weight=1.0,
            hard_failure=True,
        )



def test_canonical_and_ai_quality_vector_are_byte_identical() -> None:
    assert MODULE_PATH.read_bytes() == MIRROR_PATH.read_bytes()
