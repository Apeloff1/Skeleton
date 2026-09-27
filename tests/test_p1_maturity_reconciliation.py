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
    ROOT / "skeleton/contracts/maturity_reconciliation.py",
    ROOT / "scripts/reconcile_p1_maturity.py",
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


def test_unsigned_records_never_reach_their_lane_floor() -> None:
    module = _module()

    report = module.reconcile_repository(ROOT)

    for row in report["records"]:
        if row["implementation_signed"] is False:
            assert row["target_floor_eligible"] is False
        if (
            row["target_floor"] in {"verified", "hardened", "production"}
            and row["verification_signed"] is False
        ):
            assert row["target_floor_eligible"] is False


def test_report_identity_matches_canonical_volume_and_accountability() -> None:
    module = _module()

    report = module.reconcile_repository(
        ROOT,
        selected_volumes=("VOL-000",),
    )
    row = _row(report, "VOL-000")

    assert row["volume_key"] == "VOL-000"
    assert row["accountability_id"] == "ACC-VOL-000"
    assert row["target_floor"] == "verified"
    assert len(row["source_digest"]) == 64
    assert isinstance(row["current_claim_valid"], bool)
    assert row["current_implementation_status"] == "unverified"
    assert row["accountability_maturity_status"] is None
    assert row["implementation_status_candidate"] is None
    assert len(row["evaluations"]) == 7


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

def test_report_binds_reconciliation_engine_sources() -> None:
    module = _module()

    report = module.reconcile_repository(
        ROOT,
        selected_volumes=("VOL-000",),
    )

    assert set(report["source_digests"]) == {
        "master_plan",
        "accountability",
        "p1_execution_map",
        "engine_contract",
        "engine_runner",
    }
    assert all(
        len(value) == 64
        for value in report["source_digests"].values()
    )

