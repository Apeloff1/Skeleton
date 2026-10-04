from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from skeleton.persistence.deletion_tombstones import (
    DeletionConflict,
    DeletionCorruption,
    DeletionFenced,
    SQLiteDeletionTombstoneLedger,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DeletionTombstoneTests(unittest.TestCase):
    def test_deletion_fences_stale_generations_and_tracks_propagation(self) -> None:
        with SQLiteDeletionTombstoneLedger() as ledger:
            tombstone = ledger.request_deletion(
                tenant_id="tenant-a",
                resource_kind="memory",
                resource_id="m-1",
                deleted_through_generation=7,
                required_replicas=("cache", "vector"),
                reason_digest=sha("privacy-request"),
                now_ns=10,
            )
            with self.assertRaises(DeletionFenced):
                ledger.assert_generation_allowed(
                    tenant_id="tenant-a",
                    resource_kind="memory",
                    resource_id="m-1",
                    generation=7,
                )
            ledger.assert_generation_allowed(
                tenant_id="tenant-a",
                resource_kind="memory",
                resource_id="m-1",
                generation=8,
            )
            state = ledger.propagation_state(
                tenant_id="tenant-a",
                resource_kind="memory",
                resource_id="m-1",
            )
            self.assertFalse(state.complete)
            self.assertEqual(state.pending_replicas, ("cache", "vector"))
            ledger.acknowledge_replica(
                tenant_id="tenant-a",
                resource_kind="memory",
                resource_id="m-1",
                replica_id="cache",
                tombstone_digest=tombstone.digest,
                deleted_through_generation=7,
                now_ns=11,
            )
            self.assertEqual(
                ledger.propagation_state(
                    tenant_id="tenant-a",
                    resource_kind="memory",
                    resource_id="m-1",
                ).pending_replicas,
                ("vector",),
            )

    def test_advancing_tombstone_invalidates_previous_acknowledgements(self) -> None:
        with SQLiteDeletionTombstoneLedger() as ledger:
            first = ledger.request_deletion(
                tenant_id="tenant-a",
                resource_kind="conversation",
                resource_id="thread-1",
                deleted_through_generation=2,
                required_replicas=("search",),
                reason_digest=sha("first"),
                now_ns=20,
            )
            ledger.acknowledge_replica(
                tenant_id="tenant-a",
                resource_kind="conversation",
                resource_id="thread-1",
                replica_id="search",
                tombstone_digest=first.digest,
                deleted_through_generation=2,
                now_ns=21,
            )
            self.assertTrue(
                ledger.propagation_state(
                    tenant_id="tenant-a",
                    resource_kind="conversation",
                    resource_id="thread-1",
                ).complete
            )
            second = ledger.request_deletion(
                tenant_id="tenant-a",
                resource_kind="conversation",
                resource_id="thread-1",
                deleted_through_generation=5,
                required_replicas=("search", "warehouse"),
                reason_digest=sha("expanded"),
                now_ns=22,
            )
            self.assertEqual(second.tombstone_generation, 2)
            self.assertEqual(
                ledger.propagation_state(
                    tenant_id="tenant-a",
                    resource_kind="conversation",
                    resource_id="thread-1",
                ).acknowledged_replicas,
                (),
            )
            with self.assertRaisesRegex(DeletionConflict, "stale tombstone"):
                ledger.acknowledge_replica(
                    tenant_id="tenant-a",
                    resource_kind="conversation",
                    resource_id="thread-1",
                    replica_id="search",
                    tombstone_digest=first.digest,
                    deleted_through_generation=2,
                    now_ns=23,
                )

    def test_deletion_boundary_and_replica_set_cannot_regress(self) -> None:
        with SQLiteDeletionTombstoneLedger() as ledger:
            ledger.request_deletion(
                tenant_id="tenant-a",
                resource_kind="artifact",
                resource_id="a-1",
                deleted_through_generation=4,
                required_replicas=("blob", "index"),
                reason_digest=sha("delete"),
                now_ns=30,
            )
            with self.assertRaisesRegex(DeletionConflict, "cannot regress"):
                ledger.request_deletion(
                    tenant_id="tenant-a",
                    resource_kind="artifact",
                    resource_id="a-1",
                    deleted_through_generation=3,
                    required_replicas=("blob", "index"),
                    reason_digest=sha("delete"),
                    now_ns=31,
                )
            with self.assertRaisesRegex(DeletionConflict, "cannot shrink"):
                ledger.request_deletion(
                    tenant_id="tenant-a",
                    resource_kind="artifact",
                    resource_id="a-1",
                    deleted_through_generation=4,
                    required_replicas=("blob",),
                    reason_digest=sha("delete"),
                    now_ns=31,
                )

    def test_compaction_certificate_requires_complete_current_propagation(self) -> None:
        with SQLiteDeletionTombstoneLedger() as ledger:
            tombstone = ledger.request_deletion(
                tenant_id="tenant-a",
                resource_kind="profile",
                resource_id="p-1",
                deleted_through_generation=1,
                required_replicas=("cache", "primary"),
                reason_digest=sha("erase"),
                now_ns=40,
            )
            with self.assertRaisesRegex(DeletionConflict, "incomplete"):
                ledger.compaction_certificate(
                    tenant_id="tenant-a",
                    resource_kind="profile",
                    resource_id="p-1",
                    now_ns=41,
                )
            for index, replica in enumerate(("cache", "primary"), start=42):
                ledger.acknowledge_replica(
                    tenant_id="tenant-a",
                    resource_kind="profile",
                    resource_id="p-1",
                    replica_id=replica,
                    tombstone_digest=tombstone.digest,
                    deleted_through_generation=1,
                    now_ns=index,
                )
            certificate = ledger.compaction_certificate(
                tenant_id="tenant-a",
                resource_kind="profile",
                resource_id="p-1",
                now_ns=50,
            )
            self.assertEqual(certificate.tombstone_digest, tombstone.digest)
            self.assertEqual(certificate.acknowledged_replicas, ("cache", "primary"))
            self.assertIsNotNone(
                ledger.get(
                    tenant_id="tenant-a",
                    resource_kind="profile",
                    resource_id="p-1",
                )
            )

    def test_tenant_scope_and_restart_preserve_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deletion.db"
            with SQLiteDeletionTombstoneLedger(path) as ledger:
                ledger.request_deletion(
                    tenant_id="tenant-a",
                    resource_kind="memory",
                    resource_id="shared-name",
                    deleted_through_generation=9,
                    required_replicas=("primary",),
                    reason_digest=sha("delete"),
                    now_ns=60,
                )
                ledger.assert_generation_allowed(
                    tenant_id="tenant-b",
                    resource_kind="memory",
                    resource_id="shared-name",
                    generation=1,
                )
            with SQLiteDeletionTombstoneLedger(path) as reopened:
                with self.assertRaises(DeletionFenced):
                    reopened.assert_generation_allowed(
                        tenant_id="tenant-a",
                        resource_kind="memory",
                        resource_id="shared-name",
                        generation=9,
                    )
                self.assertEqual(
                    reopened.get(
                        tenant_id="tenant-a",
                        resource_kind="memory",
                        resource_id="shared-name",
                    ).tombstone_generation,
                    1,
                )

    def test_persisted_tombstone_digest_corruption_fails_closed(self) -> None:
        with SQLiteDeletionTombstoneLedger() as ledger:
            ledger.request_deletion(
                tenant_id="tenant-a",
                resource_kind="memory",
                resource_id="m-2",
                deleted_through_generation=3,
                required_replicas=("primary",),
                reason_digest=sha("delete"),
                now_ns=70,
            )
            ledger._connection.execute(
                "UPDATE deletion_tombstone SET tombstone_digest=?",
                ("0" * 64,),
            )
            with self.assertRaisesRegex(DeletionCorruption, "digest mismatch"):
                ledger.get(
                    tenant_id="tenant-a",
                    resource_kind="memory",
                    resource_id="m-2",
                )


if __name__ == "__main__":
    unittest.main()
