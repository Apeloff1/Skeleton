from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reconcile_p1_maturity.py"
SOURCE_PATHS = (
    ROOT / "machine/ai_master_plan.json",
    ROOT / "machine/ai_build_accountability.json",
    ROOT / "machine/ai_p1_execution_map.json",
)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "reconcile_p1_maturity",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digests() -> tuple[str, ...]:
    return tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SOURCE_PATHS
    )


def _row(report: dict, key: str) -> dict:
    return next(item for item in report["records"] if item["volume_key"] == key)


def test_live_p1_frontier_reconciliation_is_non_mutating() -> None:
    module = _module()
    before = _digests()

    report = module.reconcile_repository(ROOT)

    after = _digests()
    assert before == after
    assert report["source_mutation_detected"] is False
    assert report["volume_count"] == 107
    assert len(report["report_digest"]) == 64


def test_current_unsigned_frontier_cannot_reach_lane_floors() -> None:
    module = _module()

    report = module.reconcile_repository(ROOT)

    assert report["target_floor_eligible_count"] == 0
    assert all(
        row["implementation_signed"] is False
        for row in report["records"]
    )
    assert all(
        row["verification_signed"] is False
        for row in report["records"]
    )
    assert all(
        row["promotion_candidate"] in {None, "scaffolded"}
        for row in report["records"]
    )


def test_plan_constitution_is_only_a_scaffold_candidate_today() -> None:
    module = _module()

    report = module.reconcile_repository(
        ROOT,
        selected_volumes=("VOL-000",),
    )
    row = _row(report, "VOL-000")

    assert row["current_status"] == "specified"
    assert row["accountability_status"] == "unverified"
    assert row["promotion_candidate"] == "scaffolded"
    assert row["target_floor"] == "verified"
    assert row["target_floor_eligible"] is False


def test_planned_gap_ledger_tests_do_not_count_as_implemented() -> None:
    module = _module()

    report = module.reconcile_repository(
        ROOT,
        selected_volumes=("VOL-056",),
    )
    row = _row(report, "VOL-056")
    implemented = next(
        item for item in row["evaluations"]
        if item["state"] == "implemented"
    )

    assert implemented["eligible"] is False
    assert any(
        "tests must contain materialized references" in blocker
        for blocker in implemented["blockers"]
    )


def test_reconciliation_report_is_deterministic() -> None:
    module = _module()

    left = module.reconcile_repository(
        ROOT,
        selected_volumes=("VOL-000", "VOL-056", "VOL-080"),
    )
    right = module.reconcile_repository(
        ROOT,
        selected_volumes=("VOL-080", "VOL-000", "VOL-056"),
    )

    assert left == right
    assert left["report_digest"] == right["report_digest"]


def test_reconciliation_rejects_non_p1_volume_selection() -> None:
    module = _module()

    with pytest.raises(
        module.ReconciliationError,
        match="outside P1 primary scope",
    ):
        module.reconcile_repository(
            ROOT,
            selected_volumes=("VOL-001",),
        )
