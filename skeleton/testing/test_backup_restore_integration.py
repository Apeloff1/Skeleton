from __future__ import annotations

import hashlib
import json

from skeleton.contracts.canonical import EvidenceRef
from skeleton.persistence.snapshots import SnapshotStore
from skeleton.release.migration import MigrationCompatibilityDecision
from skeleton.release.restore import (
    BackupComponent,
    BackupComponentRole,
    BackupManifest,
    RestoreComponentReceipt,
    qualify_backup_restore,
)


COMMIT = "a" * 40


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _migration() -> MigrationCompatibilityDecision:
    return MigrationCompatibilityDecision(
        accepted=True,
        reasons=(),
        source_commit=COMMIT,
        lifecycle_qualification_digest="1" * 64,
        plan_digest="2" * 64,
        rollback_window_digest="3" * 64,
        from_version="15.0.0",
        to_version="16.0.0",
        receipt_digests=("4" * 64,),
    )


def test_snapshot_store_restore_drill_qualifies_real_semantics(
    tmp_path,
) -> None:
    store = SnapshotStore(tmp_path / "snapshots")
    authoritative = {
        "operations": [
            {
                "operation_id": "operation-1",
                "tenant_id": "tenant-1",
                "state": "completed",
                "version": 6,
            }
        ]
    }
    source_digest = _digest(authoritative)
    backup_path = store.save("operations", authoritative)
    backup_artifact_digest = hashlib.sha256(
        backup_path.read_bytes()
    ).hexdigest()

    restored = store.load("operations")
    assert restored == authoritative
    restored_digest = _digest(restored)

    derived = {
        "by_tenant": {
            "tenant-1": ["operation-1"],
        }
    }
    derived_digest = _digest(derived)
    rebuild_recipe_digest = _digest(
        {
            "recipe": "group-operation-id-by-tenant",
            "version": 1,
        }
    )

    migration = _migration()
    operations = BackupComponent(
        component_id="operations",
        role=BackupComponentRole.AUTHORITATIVE,
        source_state_digest=source_digest,
        restore_order=1,
        backup_artifact_digest=backup_artifact_digest,
    )
    search = BackupComponent(
        component_id="operation-by-tenant-index",
        role=BackupComponentRole.DERIVED,
        source_state_digest=derived_digest,
        restore_order=2,
        dependencies=("operations",),
        rebuild_recipe_digest=rebuild_recipe_digest,
    )
    manifest = BackupManifest(
        backup_id="integration-backup",
        source_commit=COMMIT,
        migration_compatibility_digest=migration.decision_digest,
        components=(operations, search),
        backup_environment_digest="5" * 64,
    )

    operation_receipt = RestoreComponentReceipt(
        component_id=operations.component_id,
        component_digest=operations.digest,
        source_commit=COMMIT,
        manifest_digest=manifest.manifest_digest,
        restore_order=operations.restore_order,
        completed_dependencies=(),
        observed_backup_artifact_digest=backup_artifact_digest,
        restored_state_digest=restored_digest,
        verifier_id="integration:operations",
        verifier_digest="6" * 64,
        test_manifest_digest="7" * 64,
        evidence_refs=(
            EvidenceRef(
                source="integration://restore/operations",
                digest="8" * 64,
                category="restore_drill",
            ),
        ),
        restored=True,
        rebuilt=False,
        independent=True,
        production_mutation_count=0,
    )
    derived_receipt = RestoreComponentReceipt(
        component_id=search.component_id,
        component_digest=search.digest,
        source_commit=COMMIT,
        manifest_digest=manifest.manifest_digest,
        restore_order=search.restore_order,
        completed_dependencies=search.dependencies,
        rebuild_recipe_digest=rebuild_recipe_digest,
        rebuild_input_digest=manifest.authoritative_state_digest,
        rebuilt_state_digest=derived_digest,
        verifier_id="integration:derived-index",
        verifier_digest="9" * 64,
        test_manifest_digest="a" * 64,
        evidence_refs=(
            EvidenceRef(
                source="integration://restore/derived-index",
                digest="b" * 64,
                category="restore_drill",
            ),
        ),
        restored=False,
        rebuilt=True,
        independent=True,
        production_mutation_count=0,
    )

    decision = qualify_backup_restore(
        migration_compatibility=migration,
        manifest=manifest,
        receipts=(operation_receipt, derived_receipt),
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert (
        decision.authoritative_state_digest
        == manifest.authoritative_state_digest
    )


def test_corrupted_snapshot_store_backup_is_not_restorable(tmp_path) -> None:
    store = SnapshotStore(tmp_path / "snapshots")
    path = store.save("operations", {"operations": []})
    path.write_text("{not-json", encoding="utf-8")

    assert store.load("operations") is None
