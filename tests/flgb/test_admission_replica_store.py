"""Durable three-way admission snapshot replica and failover tests."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.model_runtime.admission_replica_store import AdmissionReplicaFileStore
from skeleton.ai.model_runtime.admission_replicas import (
    create_admission_replica, recover_admission_quorum,
)
from skeleton.ai.model_runtime.admission_scheduler import RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError


KEY = bytes(range(32))


class TestAdmissionReplicaFileStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = {}
        for member in ("a", "b", "c"):
            path = Path(self.tmp.name) / member
            path.mkdir()
            self.paths[member] = path
        self.store = AdmissionReplicaFileStore(self.paths)

    def build(self):
        scheduler = RuntimeAdmissionScheduler()
        scheduler.submit(BatchRequest("r1", 2, 2), kv_bytes=12)
        scheduler.admit()
        return scheduler

    def blob(self, state, member, term=5):
        return create_admission_replica(
            state, member_id=member, leader_term=term, secret_key=KEY
        )

    def write_all(self, state, term=5):
        for member in self.store.members:
            self.store.save(
                member, self.blob(state, member, term),
                secret_key=KEY, minimum_term=term, minimum_sequence=0,
            )

    def quorum(self, *, minimum_term=5, minimum_sequence=0):
        return recover_admission_quorum(
            self.store.scan().copies, members=self.store.members,
            secret_key=KEY, minimum_term=minimum_term,
            minimum_sequence=minimum_sequence,
        )

    def test_write_and_recover_three_disk_roots(self):
        state = self.build()
        self.write_all(state)
        self.assertEqual(self.quorum().scheduler.snapshot(), state.snapshot())
        self.assertEqual(self.quorum().supporters, ("a", "b", "c"))

    def test_missing_disk_can_be_repaired_from_other_two(self):
        state = self.build()
        self.write_all(state)
        (self.paths["c"] / "admission-checkpoint.json").unlink()
        degraded = self.quorum()
        self.assertEqual(degraded.repair_targets, ("c",))
        self.store.repair(
            "c", degraded, secret_key=KEY,
            minimum_term=5, minimum_sequence=state.snapshot()["sequence"],
        )
        self.assertEqual(self.quorum().supporters, ("a", "b", "c"))

    def test_corrupt_disk_requires_explicit_repair(self):
        state = self.build()
        self.write_all(state)
        target = self.paths["b"] / "admission-checkpoint.json"
        target.write_bytes(b"damaged")
        self.assertEqual(self.quorum().invalid_members, ("b",))
        with self.assertRaises(ModelRuntimeError):
            self.store.save(
                "b", self.blob(state, "b"), secret_key=KEY,
                minimum_term=5, minimum_sequence=0,
            )
        before = target.read_bytes()
        self.assertEqual(before, b"damaged")
        quorum = self.quorum()
        self.store.repair(
            "b", quorum, secret_key=KEY, minimum_term=5, minimum_sequence=0,
        )
        self.assertEqual(self.quorum().supporters, ("a", "b", "c"))

    def test_repair_refuses_wrong_member_or_mismatched_floor(self):
        state = self.build()
        self.write_all(state)
        result = self.quorum()
        with self.assertRaisesRegex(ModelRuntimeError, "target"):
            self.store.repair(
                "a", result, secret_key=KEY, minimum_term=5, minimum_sequence=0,
            )
        (self.paths["c"] / "admission-checkpoint.json").unlink()
        degraded = self.quorum()
        with self.assertRaisesRegex(ModelRuntimeError, "floor"):
            self.store.repair(
                "c", degraded, secret_key=KEY, minimum_term=6, minimum_sequence=0,
            )

    def test_save_never_overwrites_newer_state_with_stale(self):
        state = self.build()
        old = self.blob(state, "a")
        self.store.save(
            "a", old, secret_key=KEY, minimum_term=5, minimum_sequence=0,
        )
        state.submit(BatchRequest("r2", 1, 1), kv_bytes=10)
        new = self.blob(state, "a")
        self.store.save(
            "a", new, secret_key=KEY, minimum_term=5, minimum_sequence=0,
        )
        with self.assertRaisesRegex(ModelRuntimeError, "regression"):
            self.store.save(
                "a", old, secret_key=KEY, minimum_term=5, minimum_sequence=0,
            )
        self.assertEqual(self.store.read("a"), new)

    def test_same_sequence_conflicting_revision_refused(self):
        state = self.build()
        first = self.blob(state, "a", term=5)
        alternate = RuntimeAdmissionScheduler()
        alternate.submit(BatchRequest("other", 2, 2), kv_bytes=12)
        alternate.admit()
        self.assertEqual(state.snapshot()["sequence"], alternate.snapshot()["sequence"])
        second = self.blob(alternate, "a", term=5)
        self.assertNotEqual(first, second)
        self.store.save(
            "a", first, secret_key=KEY, minimum_term=5, minimum_sequence=0,
        )
        with self.assertRaisesRegex(ModelRuntimeError, "conflicting"):
            self.store.save(
                "a", second, secret_key=KEY, minimum_term=5, minimum_sequence=0,
            )
        self.assertEqual(self.store.read("a"), first)

    def test_distinct_directories_required(self):
        with self.assertRaisesRegex(ModelRuntimeError, "distinct"):
            AdmissionReplicaFileStore({
                "a": self.paths["a"], "b": self.paths["a"], "c": self.paths["c"],
            })

    def test_scan_missing_all_members_fails_closed_quorum(self):
        scanned = self.store.scan()
        self.assertEqual(scanned.copies, {"a": None, "b": None, "c": None})
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.quorum()

    def test_wrong_member_rejected_on_save(self):
        state = self.build()
        wrong = self.blob(state, "a")
        with self.assertRaisesRegex(ModelRuntimeError, "identity"):
            self.store.save(
                "b", wrong, secret_key=KEY, minimum_term=5, minimum_sequence=0,
            )

    def test_one_member_too_large_is_degraded_not_global_failure(self):
        self.write_all(self.build())
        target = self.paths["c"] / "admission-checkpoint.json"
        with target.open("wb") as stream:
            stream.truncate(17 * 1024 * 1024)
        scanned = self.store.scan()
        self.assertEqual(scanned.io_failures, ("c",))
        recovered = self.quorum()
        self.assertEqual(recovered.supporters, ("a", "b"))

    def test_invalid_member_identity_rejected(self):
        for member in ("../a", "", "A", "x" * 65):
            with self.subTest(member=member), self.assertRaises(ModelRuntimeError):
                self.store.read(member)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_target_is_not_followed(self):
        state = self.build()
        self.write_all(state)
        victim = self.paths["b"] / "admission-checkpoint.json"
        alternate = self.paths["a"] / "admission-checkpoint.json"
        victim.unlink()
        try:
            victim.symlink_to(alternate)
        except (OSError, NotImplementedError):
            self.skipTest("symlink permission unavailable")
        self.assertIn("b", self.store.scan().io_failures)
        with self.assertRaises(ModelRuntimeError):
            self.store.save(
                "b", self.blob(state, "b"), secret_key=KEY,
                minimum_term=5, minimum_sequence=0,
            )
        self.assertEqual(alternate.read_bytes(), self.blob(state, "a"))

    def test_end_to_end_checkpoint_recovery_and_request_lifecycle(self):
        state = self.build()
        state.submit(BatchRequest("queued", 1, 1), kv_bytes=10)
        issued = self.store.publish(
            state, leader_term=5, secret_key=KEY,
            minimum_term=5, minimum_sequence=state.snapshot()["sequence"],
        )
        (self.paths["b"] / "admission-checkpoint.json").unlink()
        resumed = self.quorum(
            minimum_term=5, minimum_sequence=issued.sequence,
        )
        self.assertEqual(resumed.scheduler.snapshot(), state.snapshot())
        resumed.scheduler.cancel("queued")
        resumed.scheduler.complete("r1")
        resumed.scheduler.submit(BatchRequest("next", 1, 1), kv_bytes=10)
        self.assertEqual(resumed.scheduler.admit().admitted, ("next",))
        self.assertEqual(
            resumed.scheduler.capacity()["active_requests"], 1,
        )
        committed = self.store.publish(
            resumed.scheduler, leader_term=6, secret_key=KEY,
            minimum_term=5, minimum_sequence=issued.sequence,
            parent_digest=issued.snapshot_digest,
        )
        result = self.quorum(
            minimum_term=6, minimum_sequence=committed.sequence,
        )
        self.assertEqual(result.scheduler.snapshot(), resumed.scheduler.snapshot())
        self.assertEqual(result.parent_digest, issued.snapshot_digest)

    def test_fresh_leadership_floor_blocks_old_majority_until_replication(self):
        state = self.build()
        self.write_all(state)
        stale = state.snapshot()["sequence"]
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.quorum(minimum_term=6, minimum_sequence=stale)
        state.submit(BatchRequest("new", 1, 1), kv_bytes=10)
        self.store.publish(
            state, leader_term=6, secret_key=KEY,
            minimum_term=6, minimum_sequence=stale,
        )
        self.assertEqual(
            self.quorum(minimum_term=6, minimum_sequence=stale).leader_term, 6,
        )

    def test_publish_requires_two_confirmed_independent_copies(self):
        state = self.build()
        receipt = self.store.publish(
            state, leader_term=5, secret_key=KEY,
            minimum_term=5, minimum_sequence=state.snapshot()["sequence"],
        )
        self.assertEqual(receipt.committed_members, ("a", "b", "c"))
        self.assertEqual(receipt.snapshot_digest, state.snapshot()["digest"])
        self.assertEqual(self.quorum().supporters, ("a", "b", "c"))

    def test_publish_one_write_failure_still_meets_quorum(self):
        from unittest.mock import patch
        state = self.build()
        save = self.store.save
        def selective(member, blob, **kwargs):
            if member == "b":
                raise OSError("simulated b disk outage")
            return save(member, blob, **kwargs)
        with patch.object(self.store, "save", side_effect=selective):
            receipt = self.store.publish(
                state, leader_term=5, secret_key=KEY,
                minimum_term=5, minimum_sequence=0,
            )
        self.assertEqual(receipt.committed_members, ("a", "c"))
        self.assertEqual(receipt.failed_members, ("b",))

    def test_publish_two_write_failures_never_acknowledges_commit(self):
        from unittest.mock import patch
        state = self.build()
        save = self.store.save
        def selective(member, blob, **kwargs):
            if member != "a":
                raise OSError("simulated disk outage")
            return save(member, blob, **kwargs)
        with patch.object(self.store, "save", side_effect=selective):
            with self.assertRaisesRegex(ModelRuntimeError, "durable quorum"):
                self.store.publish(
                    state, leader_term=5, secret_key=KEY,
                    minimum_term=5, minimum_sequence=0,
                )
        self.assertIsNotNone(self.store.read("a"))

    def test_repair_never_overwrites_valid_newer_term(self):
        state = self.build()
        self.write_all(state)
        state.submit(BatchRequest("r2", 1, 1), kv_bytes=10)
        newer = self.blob(state, "c", term=6)
        self.store.save(
            "c", newer, secret_key=KEY, minimum_term=5, minimum_sequence=0,
        )
        old_majority = self.quorum()
        self.assertEqual(old_majority.repair_targets, ("c",))
        with self.assertRaisesRegex(ModelRuntimeError, "newer"):
            self.store.repair(
                "c", old_majority, secret_key=KEY,
                minimum_term=5, minimum_sequence=0,
            )
        self.assertEqual(self.store.read("c"), newer)

    def test_store_does_not_create_missing_directories(self):
        with self.assertRaises(ModelRuntimeError):
            AdmissionReplicaFileStore({
                "a": self.paths["a"], "b": self.paths["b"],
                "c": self.paths["c"] / "missing",
            })


if __name__ == "__main__":
    unittest.main()
