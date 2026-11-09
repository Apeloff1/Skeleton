from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_promotion_decision_policy import (
    PromotionDecisionPolicyError,
    validate_repository,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/p1_promotion_decision_policy.json")
BACKLOG = Path("machine/ai_p1_task_backlog.json")
EXECUTION_MAP = Path("machine/ai_p1_execution_map.json")
PROM02 = Path("machine/p1_terminal_failure_journeys.json")


def _copy_authorities(tmp_path: Path) -> None:
    for path in (POLICY, BACKLOG, EXECUTION_MAP, PROM02):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())


def _load(root: Path, path: Path) -> dict:
    return json.loads((root / path).read_text(encoding="utf-8"))


def _write(root: Path, path: Path, payload: dict) -> None:
    (root / path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_repository_policy_is_valid_and_derives_deferred_scope() -> None:
    report = validate_repository(ROOT)
    assert report["valid"] is True
    assert report["task_id"] == "P1-PROM-03"
    assert report["accountability_ref"] == "ACC-P1-PROM-03"
    assert report["deferred_volume_count"] > 0
    assert (
        report["masterplan_volume_count"]
        - report["primary_p1_frontier_volume_count"]
        == report["deferred_volume_count"]
    )
    assert report["signature_method"] == "ed25519"
    assert report["maturity_mutation"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("require_exact_head", False),
        (
            "require_independent_signature_verification_for_promotion",
            False,
        ),
        ("signature_method", "hmac-sha256"),
        ("allow_unsigned_explicit_rejection", False),
        ("signer_verifier_must_differ", False),
        ("deferred_scope_must_match_execution_map", False),
        ("maturity_mutation", True),
    ),
)
def test_policy_weakening_fails_closed(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    _copy_authorities(tmp_path)
    policy = _load(tmp_path, POLICY)
    policy[field] = value
    _write(tmp_path, POLICY, policy)

    with pytest.raises(PromotionDecisionPolicyError):
        validate_repository(tmp_path)


def test_deferred_count_drift_fails_closed(tmp_path: Path) -> None:
    _copy_authorities(tmp_path)
    execution = _load(tmp_path, EXECUTION_MAP)
    execution["scope_summary"]["deferred_volume_count"] += 1
    _write(tmp_path, EXECUTION_MAP, execution)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="deferred volume count/list mismatch",
    ):
        validate_repository(tmp_path)


def test_deferred_scope_arithmetic_drift_fails_closed(
    tmp_path: Path,
) -> None:
    _copy_authorities(tmp_path)
    execution = _load(tmp_path, EXECUTION_MAP)
    execution["scope_summary"][
        "primary_p1_frontier_volume_count"
    ] += 1
    _write(tmp_path, EXECUTION_MAP, execution)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="scope arithmetic mismatch",
    ):
        validate_repository(tmp_path)


def test_stale_357_acceptance_text_is_rejected(
    tmp_path: Path,
) -> None:
    _copy_authorities(tmp_path)
    backlog = _load(tmp_path, BACKLOG)
    task = next(
        row
        for row in backlog["tasks"]
        if row["task_id"] == "P1-PROM-03"
    )
    task["acceptance"][0] = (
        "Promotion leaves deferred 357-volume work visible."
    )
    _write(tmp_path, BACKLOG, backlog)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="stale deferred-volume count",
    ):
        validate_repository(tmp_path)


def test_prom02_cannot_gain_signature_authority(
    tmp_path: Path,
) -> None:
    _copy_authorities(tmp_path)
    prom02 = _load(tmp_path, PROM02)
    prom02["signed_promotion"] = True
    _write(tmp_path, PROM02, prom02)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="unexpectedly signs promotion",
    ):
        validate_repository(tmp_path)
