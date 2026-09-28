from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_p1_promotion_decision import (
    BACKLOG_PATH,
    EXECUTION_MAP_PATH,
    MASTER_PLAN_PATH,
    POLICY_PATH,
    PROM02_POLICY_PATH,
    PromotionDecisionPolicyError,
    ROOT,
    validate_repository,
)


def _repo(tmp_path: Path) -> Path:
    for relative in (
        POLICY_PATH,
        EXECUTION_MAP_PATH,
        BACKLOG_PATH,
        PROM02_POLICY_PATH,
        MASTER_PLAN_PATH,
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def _mutate(root: Path, relative: Path, mutate) -> None:
    path = root / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_current_prom03_policy_is_valid() -> None:
    summary = validate_repository(ROOT)

    assert summary == {
        "schema_version": 1,
        "task_id": "P1-PROM-03",
        "accountability_ref": "ACC-P1-PROM-03",
        "primary_volume_count": 107,
        "deferred_volume_count": 314,
        "masterplan_volume_count": 421,
        "signoff_phase_count": 2,
        "signature_method_count": 5,
        "p1_promotion_authority": True,
        "masterplan_maturity_authority": False,
        "valid": True,
    }


def test_prom03_rejects_hard_coded_deferred_count(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def mutate(payload: dict) -> None:
        task = next(
            item for item in payload["tasks"]
            if item["task_id"] == "P1-PROM-03"
        )
        task["acceptance"][0] = (
            "Promotion is exact-head and leaves deferred 314-volume work visible."
        )

    _mutate(root, BACKLOG_PATH, mutate)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="must not hard-code deferred volume count",
    ):
        validate_repository(root)


def test_prom03_rejects_dependency_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def mutate(payload: dict) -> None:
        task = next(
            item for item in payload["tasks"]
            if item["task_id"] == "P1-PROM-03"
        )
        task["depends_on"] = ["P1-PROM-01"]

    _mutate(root, BACKLOG_PATH, mutate)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="dependency identity drift",
    ):
        validate_repository(root)


def test_prom03_rejects_masterplan_maturity_authority(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda payload: payload.__setitem__(
            "masterplan_maturity_authority",
            True,
        ),
    )

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="must not carry masterplan maturity authority",
    ):
        validate_repository(root)


def test_prom03_rejects_deferred_count_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def mutate(payload: dict) -> None:
        payload["scope_summary"]["deferred_volume_count"] -= 1

    _mutate(root, EXECUTION_MAP_PATH, mutate)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="deferred volume count must equal deferred ref count",
    ):
        validate_repository(root)


def test_prom03_rejects_signature_method_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def mutate(payload: dict) -> None:
        payload["allowed_signature_methods"].append("manual")

    _mutate(root, POLICY_PATH, mutate)

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="signature method allowlist drift",
    ):
        validate_repository(root)


def test_prom03_rejects_prom02_authority_escalation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        PROM02_POLICY_PATH,
        lambda payload: payload.__setitem__("promotion_authority", True),
    )

    with pytest.raises(
        PromotionDecisionPolicyError,
        match="PROM-02 unexpectedly carries promotion authority",
    ):
        validate_repository(root)
