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
        second = self.blob(state, "a", term=5)
        self.assertEqual(first, second)
        self.store.save(
            "a", first, secret_key=KEY, minimum_term=5, minimum_sequence=0,
        )
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

    def test_store_does_not_create_missing_directories(self):
        with self.assertRaises(ModelRuntimeError):
            AdmissionReplicaFileStore({
                "a": self.paths["a"], "b": self.paths["b"],
                "c": self.paths["c"] / "missing",
            })


if __name__ == "__main__":
    unittest.main()
