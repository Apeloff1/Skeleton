from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_p1_maturity_closure_ledger.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_p1_maturity_closure_ledger",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closure_ledger_covers_full_p1_primary_frontier() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)

    assert ledger["primary_volume_count"] == 107
    assert ledger["target_floor_eligible_count"] == 3
    assert ledger["blocked_volume_count"] == 104
    assert ledger["target_floor_eligible_volume_keys"] == [
        "VOL-013",
        "VOL-014",
        "VOL-253",
    ]
    assert len(ledger["blocked_volume_keys"]) == 104
    assert len(ledger["records"]) == 107
    assert len(ledger["ledger_digest"]) == 64


def test_closure_ledger_is_non_authoritative() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)

    assert ledger["non_authoritative"] is True
    assert ledger["promotion_authority"] is False
    assert ledger["may_self_sign"] is False
    assert ledger["may_mutate_maturity"] is False

    for row in ledger["records"]:
        assert row["promotion_authority"] is False
        assert row["may_self_sign"] is False
        assert row["may_mutate_maturity"] is False


def test_blocked_volumes_have_classified_external_actions() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)
    allowed = set(module.ALLOWED_ACTIONS)

    for row in ledger["records"]:
        actions = row["required_actions"]
        assert set(actions) <= allowed
        if row["target_floor_eligible"]:
            assert actions == []
            assert row["target_floor_blockers"] == []
        else:
            assert actions
            assert row["target_floor_blockers"]


def test_metadata_projection_removed_metadata_closure_actions() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)

    forbidden = (
        "must contain materialized references",
        "contains unresolved repository references",
    )
    for row in ledger["records"]:
        assert not any(
            marker in blocker
            for blocker in row["target_floor_blockers"]
            for marker in forbidden
        )


def test_every_volume_is_bound_to_task_evidence() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)

    for row in ledger["records"]:
        assert row["mapped_task_ids"]
        assert row["mapped_task_evidence_refs"]
        assert all(
            not reference.startswith("planned:")
            for reference in row["mapped_task_evidence_refs"]
        )


def test_action_counts_match_record_projection() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)

    expected = {
        action: sum(
            action in row["required_actions"]
            for row in ledger["records"]
        )
        for action in module.ALLOWED_ACTIONS
    }
    assert ledger["required_action_counts"] == expected


def test_lane_summary_is_exact_and_exhaustive() -> None:
    module = _module()
    ledger = module.build_ledger(ROOT)

    assert set(ledger["lane_summary"]) == {
        "P1-L0",
        "P1-L1",
        "P1-L2",
        "P1-L3",
        "P1-L4",
        "P1-L5",
        "P1-L6",
    }
    assert sum(
        row["primary_volume_count"]
        for row in ledger["lane_summary"].values()
    ) == 107
    assert sum(
        row["target_floor_eligible_count"]
        for row in ledger["lane_summary"].values()
    ) == 3
    assert sum(
        row["blocked_volume_count"]
        for row in ledger["lane_summary"].values()
    ) == 104


def test_ledger_build_does_not_mutate_canonical_sources() -> None:
    module = _module()
    sources = (
        ROOT / "machine/ai_master_plan.json",
        ROOT / "machine/ai_build_accountability.json",
        ROOT / "machine/ai_p1_task_backlog.json",
        ROOT / "machine/ai_p1_execution_map.json",
    )
    before = [path.read_bytes() for path in sources]

    module.build_ledger(ROOT)

    after = [path.read_bytes() for path in sources]
    assert before == after
