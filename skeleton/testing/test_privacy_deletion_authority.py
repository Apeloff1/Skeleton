from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from skeleton.persistence.privacy_deletion import (
    CACHE,
    COMPLETE,
    DELETED,
    DeletionConflict,
    DeletionFence,
    DeletionIncomplete,
    PRIMARY_RECORD,
    PROVENANCE_REFERENCE,
    REQUIRED_TARGET_CLASSES,
    SEARCH_INDEX,
    SQLitePrivacyDeletionAuthority,
    TOMBSTONED,
    VECTOR_INDEX,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def register_example(authority: SQLitePrivacyDeletionAuthority) -> None:
    authority.register_copy(
        tenant_id="tenant",
        subject_id="user",
        copy_id="primary",
        target_class=PRIMARY_RECORD,
        store_id="db",
        resource_ref="users/1",
        content_digest=digest("primary-content"),
    )
    authority.register_copy(
        tenant_id="tenant",
        subject_id="user",
        copy_id="search",
        target_class=SEARCH_INDEX,
        store_id="search",
        resource_ref="idx/users/1",
        content_digest=digest("search-content"),
        parent_copy_id="primary",
    )
    authority.register_copy(
        tenant_id="tenant",
        subject_id="user",
        copy_id="vector",
        target_class=VECTOR_INDEX,
        store_id="vectors",
        resource_ref="vec/users/1",
        content_digest=digest("embedding"),
        parent_copy_id="primary",
    )
    authority.register_copy(
        tenant_id="tenant",
        subject_id="user",
        copy_id="provenance",
        target_class=PROVENANCE_REFERENCE,
        store_id="evidence",
        resource_ref="provenance/users/1",
        content_digest=digest("reference"),
        parent_copy_id="primary",
    )


class PrivacyDeletionAuthorityTests(unittest.TestCase):
    def test_deletion_is_identity_bound_and_permanently_fences_materialization(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            register_example(authority)
            first = authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("privacy-request"),
            )
            retry = authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("privacy-request"),
            )
            self.assertEqual(first, retry)
            with self.assertRaises(DeletionConflict):
                authority.request_deletion(
                    tenant_id="tenant",
                    subject_id="user",
                    deletion_id="delete-2",
                    request_digest=digest("different"),
                    reason_digest=digest("privacy-request"),
                )
            with self.assertRaises(DeletionFence):
                authority.register_copy(
                    tenant_id="tenant",
                    subject_id="user",
                    copy_id="cache-after-delete",
                    target_class=CACHE,
                    store_id="cache",
                    resource_ref="cache/users/1",
                    content_digest=digest("cached"),
                )
            with self.assertRaises(DeletionFence):
                authority.assert_materialization_allowed(
                    tenant_id="tenant", subject_id="user"
                )

    def test_lineage_must_remain_inside_subject(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            authority.register_copy(
                tenant_id="tenant",
                subject_id="user-a",
                copy_id="root",
                target_class=PRIMARY_RECORD,
                store_id="db",
                resource_ref="a",
                content_digest=digest("a"),
            )
            with self.assertRaisesRegex(DeletionConflict, "parent copy"):
                authority.register_copy(
                    tenant_id="tenant",
                    subject_id="user-b",
                    copy_id="derived",
                    target_class=CACHE,
                    store_id="cache",
                    resource_ref="b",
                    content_digest=digest("b"),
                    parent_copy_id="root",
                )

    def test_provenance_requires_contentless_tombstone_resolution(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            register_example(authority)
            authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("reason"),
            )
            with self.assertRaisesRegex(DeletionConflict, "requires tombstoned"):
                authority.acknowledge_resolution(
                    tenant_id="tenant",
                    subject_id="user",
                    copy_id="provenance",
                    resolution=DELETED,
                    receipt_digest=digest("deleted"),
                )
            resolved = authority.acknowledge_resolution(
                tenant_id="tenant",
                subject_id="user",
                copy_id="provenance",
                resolution=TOMBSTONED,
                receipt_digest=digest("non-content-tombstone"),
            )
            self.assertEqual(resolved.resolution, TOMBSTONED)
            self.assertEqual(resolved.content_digest, digest("reference"))

    def test_non_provenance_targets_require_deletion(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            register_example(authority)
            authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("reason"),
            )
            with self.assertRaisesRegex(DeletionConflict, "requires deleted"):
                authority.acknowledge_resolution(
                    tenant_id="tenant",
                    subject_id="user",
                    copy_id="primary",
                    resolution=TOMBSTONED,
                    receipt_digest=digest("wrong-mode"),
                )

    def test_scan_must_exactly_match_current_active_inventory(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            register_example(authority)
            authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("reason"),
            )
            with self.assertRaisesRegex(DeletionConflict, "active-copy set"):
                authority.record_scan(
                    tenant_id="tenant",
                    subject_id="user",
                    target_class=PRIMARY_RECORD,
                    inventory_digest=digest("scan"),
                    active_copy_ids=(),
                )
            scan = authority.record_scan(
                tenant_id="tenant",
                subject_id="user",
                target_class=PRIMARY_RECORD,
                inventory_digest=digest("scan"),
                active_copy_ids=("primary",),
            )
            self.assertEqual(scan.active_copy_ids, ("primary",))

    def test_finalize_requires_resolutions_and_fresh_zero_scans_for_every_target(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            register_example(authority)
            authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("reason"),
            )
            with self.assertRaises(DeletionIncomplete):
                authority.finalize(tenant_id="tenant", subject_id="user")
            for copy_id in ("primary", "search", "vector"):
                authority.acknowledge_resolution(
                    tenant_id="tenant",
                    subject_id="user",
                    copy_id=copy_id,
                    resolution=DELETED,
                    receipt_digest=digest("receipt-" + copy_id),
                )
            authority.acknowledge_resolution(
                tenant_id="tenant",
                subject_id="user",
                copy_id="provenance",
                resolution=TOMBSTONED,
                receipt_digest=digest("receipt-provenance"),
            )
            current = authority.require_tombstone(
                tenant_id="tenant", subject_id="user"
            )
            for target in REQUIRED_TARGET_CLASSES:
                authority.record_scan(
                    tenant_id="tenant",
                    subject_id="user",
                    target_class=target,
                    inventory_digest=digest("scan-" + target + str(current.revision)),
                    active_copy_ids=(),
                )
            certificate = authority.finalize(
                tenant_id="tenant", subject_id="user"
            )
            self.assertEqual(certificate.tombstone.status, COMPLETE)
            self.assertEqual(
                len(certificate.target_scans), len(REQUIRED_TARGET_CLASSES)
            )

    def test_late_discovery_reopens_completed_deletion_and_invalidates_certificate(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            authority.request_deletion(
                tenant_id="tenant",
                subject_id="user",
                deletion_id="delete-1",
                request_digest=digest("request"),
                reason_digest=digest("reason"),
            )
            first = authority.require_tombstone(
                tenant_id="tenant", subject_id="user"
            )
            for target in REQUIRED_TARGET_CLASSES:
                authority.record_scan(
                    tenant_id="tenant",
                    subject_id="user",
                    target_class=target,
                    inventory_digest=digest("initial-" + target),
                    active_copy_ids=(),
                )
            certificate = authority.finalize(
                tenant_id="tenant", subject_id="user"
            )
            self.assertEqual(certificate.tombstone.status, COMPLETE)

            authority.discover_copy(
                tenant_id="tenant",
                subject_id="user",
                copy_id="forgotten-cache",
                target_class=CACHE,
                store_id="legacy-cache",
                resource_ref="legacy/user/1",
                content_digest=digest("forgotten-content"),
            )
            reopened = authority.require_tombstone(
                tenant_id="tenant", subject_id="user"
            )
            self.assertNotEqual(reopened.revision, first.revision)
            self.assertNotEqual(reopened.status, COMPLETE)
            with self.assertRaises(DeletionIncomplete):
                authority.certificate(
                    tenant_id="tenant", subject_id="user"
                )

    def test_restart_preserves_tombstone_and_pending_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "privacy.sqlite"
            with SQLitePrivacyDeletionAuthority(path) as first:
                first.register_copy(
                    tenant_id="tenant",
                    subject_id="user",
                    copy_id="primary",
                    target_class=PRIMARY_RECORD,
                    store_id="db",
                    resource_ref="users/1",
                    content_digest=digest("content"),
                )
                first.request_deletion(
                    tenant_id="tenant",
                    subject_id="user",
                    deletion_id="delete-1",
                    request_digest=digest("request"),
                    reason_digest=digest("reason"),
                )
            with SQLitePrivacyDeletionAuthority(path) as second:
                pending = second.pending_copies(
                    tenant_id="tenant", subject_id="user"
                )
                self.assertEqual([copy.copy_id for copy in pending], ["primary"])
                with self.assertRaises(DeletionFence):
                    second.assert_materialization_allowed(
                        tenant_id="tenant", subject_id="user"
                    )

    def test_same_subject_id_is_tenant_scoped(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            authority.request_deletion(
                tenant_id="a",
                subject_id="same",
                deletion_id="delete-a",
                request_digest=digest("a"),
                reason_digest=digest("reason-a"),
            )
            authority.assert_materialization_allowed(
                tenant_id="b", subject_id="same"
            )
            authority.register_copy(
                tenant_id="b",
                subject_id="same",
                copy_id="primary",
                target_class=PRIMARY_RECORD,
                store_id="db",
                resource_ref="b/same",
                content_digest=digest("b"),
            )

    def test_card_never_self_attests_completion(self) -> None:
        with SQLitePrivacyDeletionAuthority() as authority:
            card = authority.card()
            self.assertEqual(card["gap"], "G016")
            self.assertEqual(
                tuple(card["required_target_classes"]),
                REQUIRED_TARGET_CLASSES,
            )
            self.assertFalse(card["completion_checkbox"])
            self.assertFalse(card["implementation_signature"])
            self.assertFalse(card["verification_signature"])

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/persistence/privacy_deletion.py"
        mirror = root / "skeleton/ai/runtime/persistence/privacy_deletion.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
