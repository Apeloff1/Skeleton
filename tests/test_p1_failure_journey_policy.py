from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_failure_journey_policy import (
    FailureJourneyPolicyError,
    validate_policy,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/p1_failure_journey_policy.json")


def _payload() -> dict:
    return json.loads((ROOT / POLICY).read_text(encoding="utf-8"))


def _copy_repo(tmp_path: Path, payload: dict) -> None:
    target = tmp_path / POLICY
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for row in payload["journeys"]:
        for raw in row["test_paths"]:
            path = tmp_path / raw
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# test fixture\n", encoding="utf-8")


def test_repository_failure_journey_policy_is_valid() -> None:
    report = validate_policy(ROOT)

    assert report["valid"] is True
    assert report["task_id"] == "P1-PROM-02"
    assert report["accountability_ref"] == "ACC-P1-PROM-02"
    assert report["family_count"] == 8
    assert report["test_path_count"] == 8
    assert report["promotion_authority"] is False
    assert report["signed_promotion"] is False
    assert len(report["policy_digest"]) == 64


def test_missing_failure_family_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    payload["journeys"] = payload["journeys"][1:]
    _copy_repo(tmp_path, payload)

    with pytest.raises(
        FailureJourneyPolicyError,
        match="failure family set drift",
    ):
        validate_policy(tmp_path)


def test_assertion_policy_widening_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["journeys"][0]["required_assertions"].append(
        "self_reported_success"
    )
    _copy_repo(tmp_path, payload)

    with pytest.raises(
        FailureJourneyPolicyError,
        match="assertion policy drift",
    ):
        validate_policy(tmp_path)


def test_recovery_policy_weakening_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _payload()
    row = next(
        item
        for item in payload["journeys"]
        if item["family"] == "rollback"
    )
    row["recovery_required"] = False
    _copy_repo(tmp_path, payload)

    with pytest.raises(
        FailureJourneyPolicyError,
        match="recovery policy drift",
    ):
        validate_policy(tmp_path)


def test_missing_regression_path_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _payload()
    _copy_repo(tmp_path, payload)
    path = tmp_path / payload["journeys"][0]["test_paths"][0]
    path.unlink()

    with pytest.raises(
        FailureJourneyPolicyError,
        match="missing test path",
    ):
        validate_policy(tmp_path)


def test_promotion_authority_cannot_be_enabled(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["promotion_authority"] = True
    _copy_repo(tmp_path, payload)

    with pytest.raises(
        FailureJourneyPolicyError,
        match="cannot have promotion authority",
    ):
        validate_policy(tmp_path)
