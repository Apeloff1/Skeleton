from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.migration_tests import validate_migration_chain
from skeleton.release.lifecycle import (
    InstallerLifecycleQualificationDecision,
)
from skeleton.release.migration import (
    MigrationCompatibilityError,
    MigrationCompatibilityReceipt,
    MigrationKind,
    MigrationPlan,
    MigrationSpec,
    qualify_migration_compatibility,
)


COMMIT = "a" * 40
FROM_VERSION = "15.0.0"
TO_VERSION = "16.0.0"
WINDOW = "b" * 64


def _lifecycle(
    **overrides: object,
) -> InstallerLifecycleQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "source_commit": COMMIT,
        "release_qualification_digest": "1" * 64,
        "installer_metadata_digest": "2" * 64,
        "target_version": TO_VERSION,
        "ownership_policy_digest": "3" * 64,
        "retention_policy_digest": "4" * 64,
        "scenario_receipt_digests": ("5" * 64,),
    }
    values.update(overrides)
    return InstallerLifecycleQualificationDecision(**values)


def _spec(
    migration_id: str,
    kind: MigrationKind,
    **overrides: object,
) -> MigrationSpec:
    values: dict[str, object] = {
        "migration_id": migration_id,
        "kind": kind,
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "forward_migration_digest": "6" * 64,
        "rollback_migration_digest": "7" * 64,
        "backward_reader_digest": "8" * 64,
        "declared_reader_versions": (
            FROM_VERSION,
            TO_VERSION,
        ),
        "irreversible": False,
    }
    values.update(overrides)
    return MigrationSpec(**values)


def _plan(
    lifecycle: InstallerLifecycleQualificationDecision,
    **overrides: object,
) -> MigrationPlan:
    values: dict[str, object] = {
        "plan_id": "release-migrations-v16",
        "source_commit": lifecycle.source_commit,
        "lifecycle_qualification_digest": lifecycle.decision_digest,
        "from_version": FROM_VERSION,
        "to_version": TO_VERSION,
        "rollback_window_digest": WINDOW,
        "migrations": (
            _spec("schema-main", MigrationKind.SCHEMA),
            _spec("config-main", MigrationKind.CONFIG),
            _spec("state-main", MigrationKind.STATE),
        ),
    }
    values.update(overrides)
    return MigrationPlan(**values)


def _receipt(
    spec: MigrationSpec,
    lifecycle: InstallerLifecycleQualificationDecision,
    **overrides: object,
) -> MigrationCompatibilityReceipt:
    pre = f"{spec.kind.value}:pre".encode()
    upgraded = f"{spec.kind.value}:upgraded".encode()

    def digest(value: bytes) -> str:
        import hashlib

        return hashlib.sha256(value).hexdigest()

    values: dict[str, object] = {
        "migration_id": spec.migration_id,
        "migration_digest": spec.digest,
        "source_commit": lifecycle.source_commit,
        "lifecycle_qualification_digest": lifecycle.decision_digest,
        "rollback_window_digest": WINDOW,
        "from_version": spec.from_version,
        "to_version": spec.to_version,
        "pre_migration_snapshot_digest": digest(pre),
        "upgraded_snapshot_digest": digest(upgraded),
        "rollback_snapshot_digest": digest(pre),
        "backward_read_source_digest": digest(upgraded),
        "forward_migration_digest": spec.forward_migration_digest,
        "rollback_migration_digest": spec.rollback_migration_digest,
        "backward_reader_digest": spec.backward_reader_digest,
        "reader_version": spec.from_version,
        "verifier_id": f"verifier:{spec.migration_id}",
        "verifier_digest": "9" * 64,
        "test_manifest_digest": "a" * 64,
        "evidence_refs": (
            EvidenceRef(
                source=f"migration://{spec.migration_id}",
                digest="b" * 64,
                category="migration_compatibility",
            ),
        ),
        "forward_applied": True,
        "rollback_succeeded": True,
        "backward_read_succeeded": True,
        "independent": True,
        "production_mutation_count": 0,
    }
    values.update(overrides)
    return MigrationCompatibilityReceipt(**values)


def _fixture():
    lifecycle = _lifecycle()
    plan = _plan(lifecycle)
    receipts = tuple(
        _receipt(spec, lifecycle)
        for spec in plan.migrations
    )
    return lifecycle, plan, receipts


def _qualify(
    *,
    lifecycle=None,
    plan=None,
    receipts=None,
):
    default_lifecycle, default_plan, default_receipts = _fixture()
    return qualify_migration_compatibility(
        lifecycle_qualification=(
            default_lifecycle if lifecycle is None else lifecycle
        ),
        plan=default_plan if plan is None else plan,
        receipts=default_receipts if receipts is None else receipts,
    )



def test_canonical_migration_replay_guard_uses_envelope_contract() -> None:
    task_id = validate_migration_chain()

    assert task_id


def test_complete_migration_plan_qualifies() -> None:
    lifecycle, plan, receipts = _fixture()
    decision = qualify_migration_compatibility(
        lifecycle_qualification=lifecycle,
        plan=plan,
        receipts=receipts,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.plan_digest == plan.plan_digest
    assert decision.lifecycle_qualification_digest == lifecycle.decision_digest
    assert len(decision.receipt_digests) == 3

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "migration_rollback_compatibility"
    assert evidence.digest == decision.decision_digest


def test_lifecycle_qualification_must_be_accepted() -> None:
    lifecycle = _lifecycle(
        accepted=False,
        reasons=("forced-rejection",),
    )
    plan = _plan(lifecycle)
    receipts = tuple(
        _receipt(spec, lifecycle)
        for spec in plan.migrations
    )

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=receipts,
    )

    assert decision.accepted is False
    assert "lifecycle-qualification-rejected" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "source_commit",
            "f" * 40,
            "plan-source-commit-mismatch",
        ),
        (
            "lifecycle_qualification_digest",
            "0" * 64,
            "plan-lifecycle-digest-mismatch",
        ),
    ),
)
def test_plan_must_bind_exact_rel02_identity(
    field: str,
    value: str,
    reason: str,
) -> None:
    lifecycle = _lifecycle()
    plan = _plan(lifecycle)
    plan = replace(plan, **{field: value})

    decision = qualify_migration_compatibility(
        lifecycle_qualification=lifecycle,
        plan=plan,
        receipts=(),
    )

    assert decision.accepted is False
    assert reason in decision.reasons



def test_plan_target_version_must_match_rel02() -> None:
    lifecycle = _lifecycle(target_version="17.0.0")
    plan = _plan(lifecycle)
    receipts = tuple(
        _receipt(spec, lifecycle)
        for spec in plan.migrations
    )

    decision = qualify_migration_compatibility(
        lifecycle_qualification=lifecycle,
        plan=plan,
        receipts=receipts,
    )

    assert decision.accepted is False
    assert "plan-target-version-mismatch" in decision.reasons


def test_each_migration_requires_exactly_one_receipt() -> None:
    lifecycle, plan, receipts = _fixture()
    missing = tuple(
        item
        for item in receipts
        if item.migration_id != "config-main"
    )

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=missing,
    )

    assert decision.accepted is False
    assert "receipt-cardinality:config-main" in decision.reasons


def test_unexpected_migration_receipt_blocks() -> None:
    lifecycle, plan, receipts = _fixture()
    extra_spec = _spec("unexpected", MigrationKind.CONFIG)
    extra = _receipt(extra_spec, lifecycle)

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=(*receipts, extra),
    )

    assert decision.accepted is False
    assert "unexpected-migration-receipt:unexpected" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("migration_digest", "0" * 64, "migration-digest-mismatch"),
        ("source_commit", "f" * 40, "source-commit-mismatch"),
        (
            "lifecycle_qualification_digest",
            "0" * 64,
            "lifecycle-digest-mismatch",
        ),
        (
            "rollback_window_digest",
            "0" * 64,
            "rollback-window-mismatch",
        ),
        ("from_version", "14.0.0", "from-version-mismatch"),
        ("to_version", "17.0.0", "to-version-mismatch"),
        (
            "forward_migration_digest",
            "0" * 64,
            "forward-migration-mismatch",
        ),
        (
            "rollback_migration_digest",
            "0" * 64,
            "rollback-migration-mismatch",
        ),
        (
            "backward_reader_digest",
            "0" * 64,
            "backward-reader-mismatch",
        ),
    ),
)
def test_receipt_identity_substitution_blocks(
    field: str,
    value: str,
    suffix: str,
) -> None:
    lifecycle, plan, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(rows[0], **{field: value})

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert f"schema-main:{suffix}" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("forward_applied", False, "forward-not-applied"),
        ("rollback_succeeded", False, "rollback-failed"),
        (
            "backward_read_succeeded",
            False,
            "backward-read-failed",
        ),
        ("independent", False, "not-independent"),
        ("production_mutation_count", 1, "production-mutated"),
    ),
)
def test_execution_evidence_failures_block(
    field: str,
    value: object,
    suffix: str,
) -> None:
    lifecycle, plan, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(rows[0], **{field: value})

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert f"schema-main:{suffix}" in decision.reasons


def test_rollback_must_restore_exact_pre_migration_snapshot() -> None:
    lifecycle, plan, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(
        rows[0],
        rollback_snapshot_digest="0" * 64,
    )

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert "schema-main:rollback-snapshot-mismatch" in decision.reasons


def test_backward_reader_must_read_exact_upgraded_snapshot() -> None:
    lifecycle, plan, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(
        rows[0],
        backward_read_source_digest="0" * 64,
    )

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert "schema-main:backward-read-source-mismatch" in decision.reasons


def test_reader_version_must_be_rollback_source_within_window() -> None:
    lifecycle, plan, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(
        rows[0],
        reader_version=TO_VERSION,
    )

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert "schema-main:rollback-reader-version-mismatch" in decision.reasons


def test_reader_outside_declared_window_blocks() -> None:
    lifecycle, plan, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(
        rows[0],
        reader_version="14.0.0",
    )

    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert "schema-main:reader-version-outside-window" in decision.reasons


def test_irreversible_migration_cannot_enter_rel03_plan() -> None:
    with pytest.raises(
        MigrationCompatibilityError,
        match="cannot qualify irreversible migration",
    ):
        _spec(
            "schema-main",
            MigrationKind.SCHEMA,
            irreversible=True,
        )


def test_plan_rejects_migration_version_drift() -> None:
    lifecycle = _lifecycle()
    bad = _spec(
        "config-main",
        MigrationKind.CONFIG,
        from_version="14.0.0",
        declared_reader_versions=("14.0.0", TO_VERSION),
    )

    with pytest.raises(
        MigrationCompatibilityError,
        match="from_version drift",
    ):
        _plan(
            lifecycle,
            migrations=(bad,),
        )


def test_receipt_requires_migration_compatibility_evidence() -> None:
    lifecycle = _lifecycle()
    spec = _spec("schema-main", MigrationKind.SCHEMA)

    with pytest.raises(
        MigrationCompatibilityError,
        match="requires migration_compatibility evidence",
    ):
        _receipt(
            spec,
            lifecycle,
            evidence_refs=(
                EvidenceRef(
                    source="migration://wrong",
                    digest="0" * 64,
                    category="wrong",
                ),
            ),
        )


def test_rejected_migration_cannot_materialize_promotion_evidence() -> None:
    lifecycle, plan, receipts = _fixture()
    decision = _qualify(
        lifecycle=lifecycle,
        plan=plan,
        receipts=receipts[:-1],
    )

    assert decision.accepted is False
    with pytest.raises(
        MigrationCompatibilityError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
