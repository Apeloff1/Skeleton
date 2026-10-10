from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.state_migration_compatibility import (
    MigrationCompatibilityError,
    QUALIFICATION_GAP,
    ROOT,
    _legacy_execution_rehearsal,
    _legacy_quota_rehearsal,
    _legacy_tool_receipt_rehearsal,
    _verify_masterplan,
    _verify_topology_maturity,
    _verify_workflow_binding,
)


def test_execution_legacy_schema_migrates_and_backfills_identity(
    tmp_path: Path,
) -> None:
    receipt = _legacy_execution_rehearsal(
        tmp_path / "legacy-execution.sqlite3"
    )

    assert receipt["store"] == "execution"
    assert receipt["legacy_row_preserved"] is True
    assert receipt["identity_digest_preserved"] is True
    assert receipt["state_digest_backfilled"] is True
    assert receipt["state"] == "created"
    assert receipt["version"] == 1
    assert receipt["added_digest_columns"] == {
        "ai_execution_state": "state_digest",
        "ai_execution_turn": "turn_digest",
        "ai_execution_checkpoint": "checkpoint_digest",
        "ai_execution_result": "result_digest",
        "ai_execution_outbox": "payload_digest",
    }


def test_tool_receipt_legacy_schema_adds_lineage_and_governance_defaults(
    tmp_path: Path,
) -> None:
    receipt = _legacy_tool_receipt_rehearsal(
        tmp_path / "legacy-tool-receipts.sqlite3"
    )

    assert receipt["store"] == "tool_receipts"
    assert receipt["legacy_row_preserved"] is True
    assert receipt["pending_identity_preserved"] is True
    assert receipt["lineage_defaults"] == "null"
    assert receipt["data_class_default"] == "internal"
    assert receipt["transfer_purpose_default"] == "tool-execution"
    assert receipt["added_columns"] == [
        "call_id",
        "data_class",
        "execution_id",
        "transfer_purpose",
        "turn_id",
    ]


def test_quota_legacy_schema_preserves_capacity_and_adds_storage_dimensions(
    tmp_path: Path,
) -> None:
    receipt = _legacy_quota_rehearsal(
        tmp_path / "legacy-quota.sqlite3"
    )

    assert receipt["store"] == "quota"
    assert receipt["legacy_rows_preserved"] is True
    assert receipt["max_storage_inherited_from_artifact_limit"] is True
    assert receipt["storage_usage_defaults_zero"] is True
    assert receipt["added_columns"]["tenant_quota"] == [
        "committed_storage_bytes",
        "max_storage_bytes",
    ]
    assert receipt["added_columns"]["quota_reservations"] == [
        "estimate_storage_bytes"
    ]
    assert receipt["added_columns"]["quota_completions"] == [
        "actual_storage_bytes",
        "estimate_storage_bytes",
    ]
    assert receipt["added_columns"]["quota_usage_events"] == [
        "delta_storage_bytes"
    ]


def test_current_topology_has_no_closed_gap_or_partial_authority_residue() -> None:
    receipt = _verify_topology_maturity(ROOT)

    assert receipt["topology_version"] == "1.9.0"
    assert receipt["authoritative_domain_count"] >= 13
    assert receipt["closed_gap_references"] == 0
    assert receipt["partial_authorities"] == 0
    assert "canonical-operation-state" in receipt["authoritative_domains"]
    assert "canonical-ai-memory-records" in receipt["authoritative_domains"]


def test_current_workflows_bind_migration_rehearsal_to_recovery_and_release() -> None:
    receipt = _verify_workflow_binding(ROOT)

    assert set(receipt) == {"recovery", "release"}
    assert all(len(row["digest"]) == 64 for row in receipt.values())


def test_current_masterplan_has_consistent_exact_head_qualification() -> None:
    # The independent verifier accepts either an open qualification gap or
    # a signed VOL-005 after the qualification evidence was added. Do not
    # freeze the original pre-signoff state into this regression assertion.
    binding = _verify_masterplan(ROOT)

    assert binding["key"] == "VOL-005"
    if binding["gaps"]:
        assert binding["gaps"] == [QUALIFICATION_GAP]
        assert binding["completion_checkbox"] is False
        assert binding["completion_checkbox_mark"] == "[ ]"
    else:
        assert binding["completion_checkbox"] is True
        assert binding["completion_checkbox_mark"] == "[x]"
        assert binding["implementation_status"] in {"implemented", "hardened", "verified"}
    assert len(binding["binding_digest"]) == 64


def _topology_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/state_topology.json",
        "machine/ai_app_construction.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    for relative in (
        "scripts/state_migration_compatibility.py",
        "skeleton/testing/test_state_migration_compatibility.py",
        ".github/workflows/state-recovery-drill.yml",
        ".github/workflows/p1-migration-rollback-compatibility.yml",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
    return root


def test_topology_maturity_rejects_closed_gap_reference(
    tmp_path: Path,
) -> None:
    root = _topology_fixture(tmp_path)
    topology_path = root / "machine/state_topology.json"
    topology = json.loads(topology_path.read_text(encoding="utf-8"))
    domain = next(
        row
        for row in topology["state_domains"]
        if row["id"] == "canonical-operation-state"
    )
    domain["gap"] = "gap-state-authority-convergence"
    topology_path.write_text(json.dumps(topology), encoding="utf-8")

    with pytest.raises(
        MigrationCompatibilityError,
        match="closed construction gaps still annotate state authority",
    ):
        _verify_topology_maturity(root)


def test_topology_maturity_rejects_partial_authoritative_status(
    tmp_path: Path,
) -> None:
    root = _topology_fixture(tmp_path)
    topology_path = root / "machine/state_topology.json"
    topology = json.loads(topology_path.read_text(encoding="utf-8"))
    domain = next(
        row
        for row in topology["state_domains"]
        if row["id"] == "engine-mongo-state"
    )
    domain["status"] = "declared-partial"
    topology_path.write_text(json.dumps(topology), encoding="utf-8")

    with pytest.raises(
        MigrationCompatibilityError,
        match="authoritative state remains partially bound",
    ):
        _verify_topology_maturity(root)
