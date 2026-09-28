from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.release.migration import MigrationCompatibilityDecision
from skeleton.release.restore import (
    BackupComponent,
    BackupComponentRole,
    BackupManifest,
    BackupRestoreError,
    RestoreComponentReceipt,
    qualify_backup_restore,
)


COMMIT = "a" * 40


def _migration(**overrides: object) -> MigrationCompatibilityDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "source_commit": COMMIT,
        "lifecycle_qualification_digest": "1" * 64,
        "plan_digest": "2" * 64,
        "rollback_window_digest": "3" * 64,
        "from_version": "15.0.0",
        "to_version": "16.0.0",
        "receipt_digests": ("4" * 64,),
    }
    values.update(overrides)
    return MigrationCompatibilityDecision(**values)


def _components() -> tuple[BackupComponent, ...]:
    return (
        BackupComponent(
            component_id="operations",
            role=BackupComponentRole.AUTHORITATIVE,
            source_state_digest="5" * 64,
            restore_order=1,
            backup_artifact_digest="6" * 64,
        ),
        BackupComponent(
            component_id="conversations",
            role=BackupComponentRole.AUTHORITATIVE,
            source_state_digest="7" * 64,
            restore_order=2,
            dependencies=("operations",),
            backup_artifact_digest="8" * 64,
        ),
        BackupComponent(
            component_id="search-index",
            role=BackupComponentRole.DERIVED,
            source_state_digest="9" * 64,
            restore_order=3,
            dependencies=("operations", "conversations"),
            rebuild_recipe_digest="a" * 64,
        ),
    )


def _manifest(
    migration: MigrationCompatibilityDecision,
    **overrides: object,
) -> BackupManifest:
    values: dict[str, object] = {
        "backup_id": "backup-v16",
        "source_commit": migration.source_commit,
        "migration_compatibility_digest": migration.decision_digest,
        "components": _components(),
        "backup_environment_digest": "b" * 64,
    }
    values.update(overrides)
    return BackupManifest(**values)


def _receipt(
    component: BackupComponent,
    manifest: BackupManifest,
    **overrides: object,
) -> RestoreComponentReceipt:
    values: dict[str, object] = {
        "component_id": component.component_id,
        "component_digest": component.digest,
        "source_commit": manifest.source_commit,
        "manifest_digest": manifest.manifest_digest,
        "restore_order": component.restore_order,
        "completed_dependencies": component.dependencies,
        "verifier_id": f"verifier:{component.component_id}",
        "verifier_digest": "c" * 64,
        "test_manifest_digest": "d" * 64,
        "evidence_refs": (
            EvidenceRef(
                source=f"restore://{component.component_id}",
                digest="e" * 64,
                category="restore_drill",
            ),
        ),
        "independent": True,
        "production_mutation_count": 0,
    }
    if component.role is BackupComponentRole.AUTHORITATIVE:
        values.update(
            {
                "observed_backup_artifact_digest": (
                    component.backup_artifact_digest
                ),
                "restored_state_digest": component.source_state_digest,
                "restored": True,
                "rebuilt": False,
            }
        )
    else:
        values.update(
            {
                "rebuild_recipe_digest": component.rebuild_recipe_digest,
                "rebuild_input_digest": (
                    manifest.authoritative_state_digest
                ),
                "rebuilt_state_digest": component.source_state_digest,
                "restored": False,
                "rebuilt": True,
            }
        )
    values.update(overrides)
    return RestoreComponentReceipt(**values)


def _fixture():
    migration = _migration()
    manifest = _manifest(migration)
    receipts = tuple(
        _receipt(component, manifest)
        for component in manifest.components
    )
    return migration, manifest, receipts


def _qualify(
    *,
    migration=None,
    manifest=None,
    receipts=None,
):
    default_migration, default_manifest, default_receipts = _fixture()
    return qualify_backup_restore(
        migration_compatibility=(
            default_migration if migration is None else migration
        ),
        manifest=default_manifest if manifest is None else manifest,
        receipts=default_receipts if receipts is None else receipts,
    )


def test_authoritative_restore_and_derived_rebuild_qualify() -> None:
    migration, manifest, receipts = _fixture()
    decision = qualify_backup_restore(
        migration_compatibility=migration,
        manifest=manifest,
        receipts=receipts,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.manifest_digest == manifest.manifest_digest
    assert (
        decision.authoritative_state_digest
        == manifest.authoritative_state_digest
    )
    assert len(decision.receipt_digests) == 3

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "backup_restore_qualification"
    assert evidence.digest == decision.decision_digest


def test_migration_compatibility_must_be_accepted() -> None:
    migration = _migration(
        accepted=False,
        reasons=("forced-rejection",),
    )
    manifest = _manifest(migration)
    receipts = tuple(
        _receipt(component, manifest)
        for component in manifest.components
    )

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=receipts,
    )

    assert decision.accepted is False
    assert "migration-compatibility-rejected" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "source_commit",
            "f" * 40,
            "manifest-source-commit-mismatch",
        ),
        (
            "migration_compatibility_digest",
            "0" * 64,
            "manifest-migration-digest-mismatch",
        ),
    ),
)
def test_manifest_must_bind_exact_rel03(
    field: str,
    value: str,
    reason: str,
) -> None:
    migration = _migration()
    manifest = replace(_manifest(migration), **{field: value})

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=(),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_each_component_requires_exactly_one_receipt() -> None:
    migration, manifest, receipts = _fixture()
    missing = tuple(
        item
        for item in receipts
        if item.component_id != "conversations"
    )

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=missing,
    )

    assert decision.accepted is False
    assert (
        "restore-receipt-cardinality:conversations"
        in decision.reasons
    )


def test_unexpected_restore_receipt_blocks() -> None:
    migration, manifest, receipts = _fixture()
    extra = replace(
        receipts[0],
        component_id="unexpected",
    )

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=(*receipts, extra),
    )

    assert decision.accepted is False
    assert "unexpected-restore-receipt:unexpected" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("component_digest", "0" * 64, "component-digest-mismatch"),
        ("source_commit", "f" * 40, "source-commit-mismatch"),
        ("manifest_digest", "0" * 64, "manifest-digest-mismatch"),
        ("restore_order", 9, "restore-order-mismatch"),
        (
            "completed_dependencies",
            ("unexpected",),
            "dependency-evidence-mismatch",
        ),
        ("independent", False, "not-independent"),
        ("production_mutation_count", 1, "production-mutated"),
    ),
)
def test_restore_receipt_identity_and_execution_drift_blocks(
    field: str,
    value: object,
    suffix: str,
) -> None:
    migration, manifest, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(rows[0], **{field: value})

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert f"operations:{suffix}" in decision.reasons


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"restored": False}, "operations:not-restored"),
        ({"rebuilt": True}, "operations:unexpected-rebuild"),
        (
            {"observed_backup_artifact_digest": "0" * 64},
            "operations:backup-artifact-mismatch",
        ),
        (
            {"restored_state_digest": "0" * 64},
            "operations:semantic-restore-mismatch",
        ),
        (
            {"rebuild_recipe_digest": "0" * 64},
            "operations:unexpected-rebuild-recipe",
        ),
    ),
)
def test_authoritative_restore_must_preserve_semantics(
    changes: dict[str, object],
    reason: str,
) -> None:
    migration, manifest, receipts = _fixture()
    rows = list(receipts)
    rows[0] = replace(rows[0], **changes)

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"restored": True}, "search-index:derived-state-restored-as-authority"),
        ({"rebuilt": False}, "search-index:derived-state-not-rebuilt"),
        (
            {"rebuild_recipe_digest": "0" * 64},
            "search-index:rebuild-recipe-mismatch",
        ),
        (
            {"rebuild_input_digest": "0" * 64},
            "search-index:rebuild-input-mismatch",
        ),
        (
            {"rebuilt_state_digest": "0" * 64},
            "search-index:derived-rebuild-mismatch",
        ),
    ),
)
def test_derived_state_must_rebuild_deterministically(
    changes: dict[str, object],
    reason: str,
) -> None:
    migration, manifest, receipts = _fixture()
    rows = list(receipts)
    rows[2] = replace(rows[2], **changes)

    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=tuple(rows),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_authoritative_component_requires_backup_artifact() -> None:
    with pytest.raises(
        BackupRestoreError,
        match="requires backup artifact",
    ):
        BackupComponent(
            component_id="operations",
            role=BackupComponentRole.AUTHORITATIVE,
            source_state_digest="1" * 64,
            restore_order=1,
        )


def test_derived_component_requires_rebuild_recipe_and_dependencies() -> None:
    with pytest.raises(
        BackupRestoreError,
        match="requires rebuild recipe",
    ):
        BackupComponent(
            component_id="search-index",
            role=BackupComponentRole.DERIVED,
            source_state_digest="1" * 64,
            restore_order=2,
            dependencies=("operations",),
        )

    migration = _migration()
    derived = BackupComponent(
        component_id="search-index",
        role=BackupComponentRole.DERIVED,
        source_state_digest="1" * 64,
        restore_order=2,
        rebuild_recipe_digest="2" * 64,
    )
    authoritative = BackupComponent(
        component_id="operations",
        role=BackupComponentRole.AUTHORITATIVE,
        source_state_digest="3" * 64,
        restore_order=1,
        backup_artifact_digest="4" * 64,
    )
    with pytest.raises(
        BackupRestoreError,
        match="requires restore dependencies",
    ):
        _manifest(
            migration,
            components=(authoritative, derived),
        )


def test_manifest_rejects_unknown_or_late_dependencies() -> None:
    migration = _migration()
    authoritative = BackupComponent(
        component_id="operations",
        role=BackupComponentRole.AUTHORITATIVE,
        source_state_digest="1" * 64,
        restore_order=2,
        backup_artifact_digest="2" * 64,
    )
    derived = BackupComponent(
        component_id="search-index",
        role=BackupComponentRole.DERIVED,
        source_state_digest="3" * 64,
        restore_order=1,
        dependencies=("operations",),
        rebuild_recipe_digest="4" * 64,
    )

    with pytest.raises(
        BackupRestoreError,
        match="dependency restore order invalid",
    ):
        _manifest(
            migration,
            components=(derived, authoritative),
        )

    bad = replace(
        derived,
        restore_order=3,
        dependencies=("missing",),
    )
    with pytest.raises(
        BackupRestoreError,
        match="unknown dependency",
    ):
        _manifest(
            migration,
            components=(authoritative, bad),
        )


def test_receipt_requires_restore_drill_evidence() -> None:
    migration, manifest, _ = _fixture()
    component = manifest.components[0]

    with pytest.raises(
        BackupRestoreError,
        match="requires restore_drill evidence",
    ):
        _receipt(
            component,
            manifest,
            evidence_refs=(
                EvidenceRef(
                    source="restore://wrong",
                    digest="0" * 64,
                    category="wrong",
                ),
            ),
        )


def test_rejected_restore_cannot_materialize_promotion_evidence() -> None:
    migration, manifest, receipts = _fixture()
    decision = _qualify(
        migration=migration,
        manifest=manifest,
        receipts=receipts[:-1],
    )

    assert decision.accepted is False
    with pytest.raises(
        BackupRestoreError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
