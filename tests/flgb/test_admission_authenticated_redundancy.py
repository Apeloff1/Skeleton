"""HMAC-authenticated, term-fenced adapters for canonical admission redundancy.

The tests use temporary directories and the *existing* three-way quorum
publisher/recovery, not a second majority implementation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.model_runtime.admission_redundancy import (
    AUTHENTICATED_REPLICA_SCHEMA, AuthenticatedFileCheckpointReplica,
    FileCheckpointReplica, publish_redundant_checkpoint,
    recover_redundant_checkpoint, repair_redundant_checkpoint,
)
from skeleton.ai.model_runtime.admission_scheduler import (
    AdmissionLimits, RuntimeAdmissionScheduler,
)
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


KEY = bytes(range(32))
WRONG_KEY = bytes(reversed(range(32)))
PARENT = "a" * 64
OTHER_PARENT = "b" * 64
LIMITS = AdmissionLimits(
    max_active_requests=2, max_queued_requests=3, max_batch_size=1,
    max_tokens_per_batch=30, kv_capacity_bytes=100, max_age_boost=10,
)
POLICY = RuntimePolicyCompiler().compile(2024)


class TestAuthenticatedRedundantCheckpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.locations = []
        for index in range(3):
            directory = Path(self.tmp.name) / f"disk-{index}"
            directory.mkdir()
            self.locations.append(directory / "checkpoint.json")

    def slots(self, *, term=5, key=KEY, parent=PARENT):
        return tuple(
            AuthenticatedFileCheckpointReplica(
                f"replica-{i}", f"domain-{i}",
                self.locations[i], leader_term=term,
                secret_key=key, expected_parent_digest=parent,
            ) for i in range(3)
        )

    def scheduler(self):
        scheduler = RuntimeAdmissionScheduler(LIMITS, policy=POLICY)
        scheduler.submit(BatchRequest("active", 3, 2), kv_bytes=15)
        scheduler.admit()
        scheduler.submit(BatchRequest("queued", 1, 1), kv_bytes=5)
        return scheduler

    def publish(self, value, slots=None):
        return publish_redundant_checkpoint(
            value, self.slots() if slots is None else slots,
            expected_policy=POLICY, expected_limits=LIMITS,
        )

    def recover(self, slots=None, **kwargs):
        return recover_redundant_checkpoint(
            self.slots() if slots is None else slots,
            expected_policy=POLICY, expected_limits=LIMITS, **kwargs,
        )

    def test_healthy_replicas_recover_exact_scheduler_state(self):
        scheduler = self.scheduler()
        receipt = self.publish(scheduler)
        self.assertFalse(receipt.degraded)
        recovered = self.recover()
        self.assertEqual(recovered.scheduler.snapshot(), scheduler.snapshot())
        self.assertEqual(len(recovered.matching), 3)

    def test_disk_files_are_signed_member_bound_envelopes(self):
        self.publish(self.scheduler())
        raw = json.loads(self.locations[0].read_bytes())
        self.assertEqual(raw["schema"], AUTHENTICATED_REPLICA_SCHEMA)
        self.assertEqual(raw["member"], "replica-0")
        self.assertEqual(raw["leader_term"], 5)
        self.assertEqual(raw["parent_digest"], PARENT)
        self.assertEqual(len(raw["mac"]), 64)
        self.assertEqual(raw["snapshot_digest"], raw["snapshot"]["digest"])

    def test_one_corrupt_member_is_degraded_but_recoverable(self):
        scheduler = self.scheduler()
        self.publish(scheduler)
        self.locations[1].write_bytes(b"broken")
        recovered = self.recover()
        self.assertTrue(recovered.degraded)
        self.assertEqual(recovered.scheduler.snapshot(), scheduler.snapshot())
        self.assertEqual(len(recovered.matching), 2)

    def test_two_corrupt_members_fail_closed(self):
        self.publish(self.scheduler())
        self.locations[1].write_bytes(b"broken")
        self.locations[2].write_bytes(b"broken")
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover()

    def test_modified_payload_recomputed_plain_digest_fails_hmac(self):
        self.publish(self.scheduler())
        backend = FileCheckpointReplica(
            "replica-2", "domain-2", self.locations[2]
        )
        envelope = backend.read()
        envelope["snapshot"]["capacity"]["kv_used_bytes"] = 50
        backend.write(envelope)
        with self.assertRaisesRegex(ModelRuntimeError, "HMAC"):
            self.slots()[2].read()
        self.assertTrue(self.recover().degraded)

    def test_copying_signed_record_to_other_member_is_rejected(self):
        self.publish(self.scheduler())
        self.locations[2].write_bytes(self.locations[0].read_bytes())
        with self.assertRaisesRegex(ModelRuntimeError, "member"):
            self.slots()[2].read()
        self.assertEqual(len(self.recover().matching), 2)

    def test_wrong_runtime_secret_refuses_recovery(self):
        self.publish(self.scheduler())
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(self.slots(key=WRONG_KEY))

    def test_old_term_cannot_read_newer_signed_term_or_publish_over_it(self):
        scheduler = self.scheduler()
        self.publish(scheduler, self.slots(term=6))
        stale = self.slots(term=5)
        with self.assertRaisesRegex(ModelRuntimeError, "newer leadership"):
            stale[0].read()
        with self.assertRaisesRegex(ModelRuntimeError, "newer leadership"):
            self.publish(scheduler, stale)
        self.assertEqual(self.recover(self.slots(term=6)).sequence, scheduler.snapshot()["sequence"])

    def test_higher_trusted_term_can_rotate_valid_old_term(self):
        scheduler = self.scheduler()
        self.publish(scheduler, self.slots(term=5))
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(self.slots(term=6))
        self.publish(scheduler, self.slots(term=6))
        self.assertFalse(self.recover(self.slots(term=6)).degraded)

    def test_same_term_parent_fork_prevents_publish(self):
        scheduler = self.scheduler()
        self.publish(scheduler, self.slots(parent=OTHER_PARENT))
        stale_branch = self.slots(parent=PARENT)
        with self.assertRaisesRegex(ModelRuntimeError, "parent revision conflict"):
            stale_branch[0].read()
        with self.assertRaisesRegex(ModelRuntimeError, "parent revision conflict"):
            self.publish(scheduler, stale_branch)

    def test_same_term_checkpoint_chain_advances_across_two_publications(self):
        scheduler = self.scheduler()
        first = self.publish(scheduler)
        scheduler.submit(BatchRequest("new", 1, 1), kv_bytes=10)
        chained = self.slots(parent=first.digest)
        second = self.publish(scheduler, chained)
        self.assertGreater(second.sequence, first.sequence)
        self.assertNotEqual(second.digest, first.digest)
        self.assertEqual(
            self.recover(chained, minimum_sequence=second.sequence).scheduler.snapshot(),
            scheduler.snapshot(),
        )
        for location in self.locations:
            self.assertEqual(json.loads(location.read_bytes())["parent_digest"], first.digest)

    def test_one_signed_wrong_parent_is_not_a_quorum_vote(self):
        scheduler = self.scheduler()
        self.publish(scheduler)
        alternate = self.slots(parent=OTHER_PARENT)
        alternate[2].write(scheduler.snapshot())
        self.assertEqual(len(self.recover().matching), 2)

    def test_operator_repair_regenerates_signed_third_replica(self):
        scheduler = self.scheduler()
        self.publish(scheduler)
        self.locations[2].write_bytes(b"damaged")
        receipt = repair_redundant_checkpoint(
            self.slots(), expected_policy=POLICY, expected_limits=LIMITS,
            minimum_sequence=scheduler.snapshot()["sequence"],
            expected_digest=scheduler.snapshot()["digest"],
        )
        self.assertFalse(receipt.degraded)
        self.assertEqual(len(self.recover().matching), 3)

    def test_duplicate_storage_path_under_wrappers_is_rejected(self):
        self.publish(self.scheduler())
        slots = list(self.slots())
        slots[2] = AuthenticatedFileCheckpointReplica(
            "third-name", "domain-2", self.locations[0],
            leader_term=5, secret_key=KEY, expected_parent_digest=PARENT,
        )
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate checkpoint storage path"):
            self.publish(self.scheduler(), tuple(slots))

    def test_secret_key_does_not_appear_in_object_representation(self):
        secret = b"x" * 80
        adapter = self.slots(key=secret)[0]
        self.assertNotIn(repr(secret), repr(adapter))
        self.assertNotIn("secret_key=", repr(adapter))

    def test_direct_adapter_write_refuses_newer_term(self):
        scheduler = self.scheduler()
        self.publish(scheduler, self.slots(term=6))
        with self.assertRaisesRegex(ModelRuntimeError, "newer leadership"):
            self.slots(term=5)[0].write(scheduler.snapshot())

    def test_direct_adapter_write_refuses_conflicting_same_sequence(self):
        scheduler = self.scheduler()
        self.publish(scheduler)
        alternate = self.scheduler()
        alternate.cancel("queued")
        alternate.submit(BatchRequest("other", 1, 1), kv_bytes=5)
        self.assertGreater(alternate.snapshot()["sequence"], scheduler.snapshot()["sequence"])
        # Construct a different scheduler with the exact original sequence.
        second = RuntimeAdmissionScheduler(LIMITS, policy=POLICY)
        second.submit(BatchRequest("other", 3, 2), kv_bytes=15)
        second.admit()
        second.submit(BatchRequest("queued", 1, 1), kv_bytes=5)
        self.assertEqual(second.snapshot()["sequence"], scheduler.snapshot()["sequence"])
        with self.assertRaisesRegex(ModelRuntimeError, "conflicting authenticated"):
            self.slots()[0].write(second.snapshot())

    def test_direct_adapter_write_requires_predecessor_progress(self):
        scheduler = self.scheduler()
        receipt = self.publish(scheduler)
        next_generation = self.slots(parent=receipt.digest)
        with self.assertRaisesRegex(ModelRuntimeError, "advance predecessor"):
            next_generation[0].write(scheduler.snapshot())

    def test_short_key_and_wrong_term_type_rejected_at_construction(self):
        with self.assertRaisesRegex(ModelRuntimeError, "key"):
            self.slots(key=b"bad")
        for term in (-1, True, 2**63):
            with self.subTest(term=term), self.assertRaisesRegex(
                ModelRuntimeError, "leadership term"
            ):
                self.slots(term=term)

    def test_external_digest_and_sequence_floor_apply_to_signed_recovery(self):
        scheduler = self.scheduler()
        self.publish(scheduler)
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(expected_digest="0" * 64)
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(minimum_sequence=scheduler.snapshot()["sequence"] + 1)

    def test_live_scheduler_mutation_does_not_modify_signed_disk_snapshot(self):
        scheduler = self.scheduler()
        self.publish(scheduler)
        initial = self.recover().scheduler.snapshot()
        scheduler.cancel("queued")
        self.assertNotEqual(initial, scheduler.snapshot())
        self.assertEqual(self.recover().scheduler.snapshot(), initial)


if __name__ == "__main__":
    unittest.main()
