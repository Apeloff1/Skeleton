"""Three-way checkpoint redundancy, corruption handling, crash windows and fencing."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.admission_redundancy import (
    FileCheckpointReplica, publish_redundant_checkpoint,
    recover_redundant_checkpoint, repair_redundant_checkpoint,
)
from skeleton.ai.model_runtime.admission_scheduler import (
    AdmissionLimits, RuntimeAdmissionScheduler,
)
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


LIMITS = AdmissionLimits(
    max_active_requests=3, max_queued_requests=5, max_batch_size=2,
    max_tokens_per_batch=64, kv_capacity_bytes=200, max_age_boost=20,
)
POLICY = RuntimePolicyCompiler().compile(2024)


class MemoryReplica:
    """Testing adapter; intentionally not a durable storage implementation."""

    def __init__(self, index):
        self.name = f"slot-{index}"
        self.failure_domain = f"domain-{index}"
        self.data = None
        self.read_failed = False
        self.write_failed = False
        self.corrupt_readback = False

    def read(self):
        if self.read_failed:
            raise OSError("injected read failure")
        if self.corrupt_readback and self.data is not None:
            record = copy.deepcopy(self.data)
            record["sequence"] += 1
            return record
        return copy.deepcopy(self.data)

    def write(self, snapshot):
        if self.write_failed:
            raise OSError("injected write failure")
        self.data = copy.deepcopy(snapshot)


def scheduler():
    result = RuntimeAdmissionScheduler(LIMITS, policy=POLICY)
    result.submit(BatchRequest("first", 4, 4), kv_bytes=30)
    result.admit()
    result.submit(BatchRequest("second", 2, 4), kv_bytes=25)
    return result


def slots():
    return [MemoryReplica(index) for index in range(3)]


def publish(value, replicas, **kwargs):
    return publish_redundant_checkpoint(
        value, replicas, expected_limits=LIMITS, expected_policy=POLICY, **kwargs,
    )


def recover(replicas, **kwargs):
    return recover_redundant_checkpoint(
        replicas, expected_limits=LIMITS, expected_policy=POLICY, **kwargs,
    )


class TestRedundantAdmissionRecovery(unittest.TestCase):
    def test_all_three_copy_roundtrip(self):
        live = scheduler()
        replicas = slots()
        receipt = publish(live, replicas)
        self.assertFalse(receipt.degraded)
        self.assertEqual(len(receipt.acknowledged), 3)
        restored = recover(replicas)
        self.assertEqual(restored.scheduler.snapshot(), live.snapshot())
        self.assertEqual(restored.sequence, live.snapshot()["sequence"])
        self.assertEqual(restored.digest, receipt.digest)
        self.assertFalse(restored.degraded)

    def test_external_mutation_cannot_change_replica_copy(self):
        live = scheduler()
        replicas = slots()
        publish(live, replicas)
        saved = replicas[0].read()
        saved["queued"].clear()
        self.assertEqual(recover(replicas).scheduler.snapshot(), live.snapshot())

    def test_one_failed_replica_write_recovers_by_quorum(self):
        live = scheduler()
        replicas = slots()
        replicas[2].write_failed = True
        receipt = publish(live, replicas)
        self.assertEqual(receipt.acknowledged, ("slot-0", "slot-1"))
        self.assertEqual(receipt.unavailable, ("slot-2",))
        self.assertTrue(receipt.degraded)
        result = recover(replicas)
        self.assertTrue(result.degraded)
        self.assertEqual(result.matching, ("slot-0", "slot-1"))

    def test_two_failed_replica_writes_refuse_publication(self):
        replicas = slots()
        replicas[1].write_failed = True
        replicas[2].write_failed = True
        with self.assertRaisesRegex(ModelRuntimeError, "publication lacks"):
            publish(scheduler(), replicas)

    def test_missing_one_replica_still_recovers(self):
        live = scheduler()
        replicas = slots()
        publish(live, replicas)
        replicas[1].data = None
        result = recover(replicas)
        self.assertEqual(result.matching, ("slot-0", "slot-2"))
        self.assertEqual(result.rejected, ("slot-1",))
        self.assertTrue(result.degraded)

    def test_missing_two_replicas_fails_closed(self):
        replicas = slots()
        publish(scheduler(), replicas)
        replicas[0].data = None
        replicas[2].data = None
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover(replicas)

    def test_corrupted_one_replica_cannot_poison_quorum(self):
        live = scheduler()
        replicas = slots()
        publish(live, replicas)
        replicas[0].data["queued"][0]["kv_bytes"] = 777
        result = recover(replicas)
        self.assertEqual(result.matching, ("slot-1", "slot-2"))
        self.assertEqual(result.scheduler.snapshot(), live.snapshot())

    def test_corrupted_two_replicas_refuse_restore(self):
        replicas = slots()
        publish(scheduler(), replicas)
        for replica in replicas[:2]:
            replica.data["sequence"] += 1
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover(replicas)

    def test_read_failure_degrades_but_does_not_corrupt_state(self):
        live = scheduler()
        replicas = slots()
        publish(live, replicas)
        replicas[0].read_failed = True
        self.assertEqual(recover(replicas).scheduler.snapshot(), live.snapshot())
        replicas[1].read_failed = True
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover(replicas)

    def test_mismatched_valid_revisions_without_majority_are_rejected(self):
        replicas = slots()
        first = scheduler()
        publish(first, replicas)
        for i, replica in enumerate(replicas):
            current = scheduler()
            for _ in range(i + 1):
                current.admit()
            replica.data = current.snapshot()
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover(replicas)

    def test_single_uncommitted_newer_revision_does_not_override_quorum(self):
        replicas = slots()
        live = scheduler()
        publish(live, replicas)
        old = live.snapshot()
        live.admit()
        replicas[2].data = live.snapshot()
        result = recover(replicas)
        self.assertEqual(result.digest, old["digest"])
        self.assertEqual(result.matching, ("slot-0", "slot-1"))
        self.assertTrue(result.degraded)

    def test_trusted_minimum_sequence_blocks_rollback_to_older_majority(self):
        replicas = slots()
        live = scheduler()
        publish(live, replicas)
        live.admit()
        latest = live.snapshot()
        replicas[2].data = latest
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover(replicas, minimum_sequence=latest["sequence"])

    def test_trusted_expected_digest_blocks_rollback_to_older_majority(self):
        replicas = slots()
        live = scheduler()
        publish(live, replicas)
        live.admit()
        latest = live.snapshot()
        replicas[2].data = latest
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover(replicas, expected_digest=latest["digest"])

    def test_matching_digest_pin_recovers_after_replica_failure(self):
        replicas = slots()
        live = scheduler()
        receipt = publish(live, replicas)
        replicas[0].data = None
        result = recover(
            replicas, minimum_sequence=receipt.sequence,
            expected_digest=receipt.digest,
        )
        self.assertEqual(result.digest, receipt.digest)

    def test_republication_advances_all_replicas(self):
        replicas = slots()
        live = scheduler()
        previous = publish(live, replicas)
        live.admit()
        updated = publish(live, replicas, minimum_sequence=previous.sequence)
        self.assertGreater(updated.sequence, previous.sequence)
        self.assertNotEqual(updated.digest, previous.digest)
        self.assertEqual(recover(replicas).digest, updated.digest)

    def test_preflight_prevents_stale_overwrite_and_preserves_previous(self):
        replicas = slots()
        live = scheduler()
        live.admit()
        future = publish(live, replicas)
        stale = scheduler()
        with self.assertRaisesRegex(ModelRuntimeError, "stale"):
            publish(stale, replicas)
        self.assertEqual(recover(replicas).digest, future.digest)

    def test_same_sequence_divergent_checkpoint_refuses_overwrite(self):
        replicas = slots()
        first = scheduler()
        receipt = publish(first, replicas)
        other = RuntimeAdmissionScheduler(LIMITS, policy=POLICY)
        other.submit(BatchRequest("other", 4, 4), kv_bytes=30)
        other.admit()
        other.submit(BatchRequest("next", 2, 4), kv_bytes=25)
        self.assertEqual(other.snapshot()["sequence"], receipt.sequence)
        with self.assertRaisesRegex(ModelRuntimeError, "conflicting"):
            publish(other, replicas)
        self.assertEqual(recover(replicas).digest, receipt.digest)

    def test_degraded_readback_acks_only_verified_slots(self):
        replicas = slots()
        replicas[2].corrupt_readback = True
        published = publish(scheduler(), replicas)
        self.assertTrue(published.degraded)
        self.assertEqual(published.unavailable, ("slot-2",))
        replicas[2].corrupt_readback = False
        self.assertEqual(len(recover(replicas).matching), 3)

    def test_two_corrupt_readbacks_refuse_publish(self):
        replicas = slots()
        replicas[1].corrupt_readback = True
        replicas[2].corrupt_readback = True
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            publish(scheduler(), replicas)

    def test_duplicate_adapter_object_refused(self):
        a, b, _ = slots()
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate"):
            publish(scheduler(), [a, b, a])

    def test_duplicate_domain_refused(self):
        replicas = slots()
        replicas[2].failure_domain = replicas[0].failure_domain
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate"):
            publish(scheduler(), replicas)

    def test_duplicate_name_refused(self):
        replicas = slots()
        replicas[1].name = replicas[0].name
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate"):
            recover(replicas)

    def test_wrong_replica_count_refused(self):
        for replicas in ([], slots()[:2], slots() + [MemoryReplica(4)]):
            with self.subTest(size=len(replicas)), self.assertRaisesRegex(
                ModelRuntimeError, "exactly three"
            ):
                recover(replicas)

    def test_malformed_trusted_revision_pins_fail_closed(self):
        replicas = slots()
        publish(scheduler(), replicas)
        for floor in (True, "1", -1, 1.5):
            with self.subTest(floor=floor), self.assertRaisesRegex(
                ModelRuntimeError, "sequence floor"
            ):
                recover(replicas, minimum_sequence=floor)
        for digest in (None, "0" * 63, "💥" * 64, 1234):
            if digest is None:
                continue
            with self.subTest(digest=repr(digest)), self.assertRaises(ModelRuntimeError):
                recover(replicas, expected_digest=digest)

    def test_quorum_recovery_requires_exact_deployment_limits(self):
        replicas = slots()
        publish(scheduler(), replicas)
        other = AdmissionLimits()
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover_redundant_checkpoint(replicas, expected_limits=other)

    def test_quorum_recovery_requires_expected_policy(self):
        replicas = slots()
        publish(scheduler(), replicas)
        other = RuntimePolicyCompiler().compile(2023)
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            recover_redundant_checkpoint(replicas, expected_policy=other)

    def test_repair_rebuilds_deleted_copy_from_trusted_quorum(self):
        replicas = slots()
        live = scheduler()
        witness = publish(live, replicas)
        replicas[2].data = None
        repaired = repair_redundant_checkpoint(
            replicas,
            expected_policy=POLICY, expected_limits=LIMITS,
            minimum_sequence=witness.sequence,
            expected_digest=witness.digest,
        )
        self.assertFalse(repaired.degraded)
        self.assertEqual(repaired.acknowledged, ("slot-0", "slot-1", "slot-2"))
        self.assertEqual(recover(replicas).scheduler.snapshot(), live.snapshot())

    def test_repair_refuses_without_two_valid_copies(self):
        replicas = slots()
        witness = publish(scheduler(), replicas)
        replicas[0].data = None
        replicas[1].data["digest"] = "0" * 64
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            repair_redundant_checkpoint(
                replicas,
                expected_policy=POLICY, expected_limits=LIMITS,
                expected_digest=witness.digest,
            )
        self.assertIsNone(replicas[0].data)

    def test_repair_never_overwrites_newer_nonquorum_revision(self):
        replicas = slots()
        live = scheduler()
        publish(live, replicas)
        live.admit()
        latest = live.snapshot()
        replicas[2].data = latest
        with self.assertRaisesRegex(ModelRuntimeError, "stale"):
            repair_redundant_checkpoint(
                replicas, expected_policy=POLICY, expected_limits=LIMITS,
            )
        self.assertEqual(replicas[2].data, latest)

    def test_repair_degraded_when_third_storage_is_unavailable(self):
        replicas = slots()
        receipt = publish(scheduler(), replicas)
        replicas[2].data = None
        replicas[2].write_failed = True
        result = repair_redundant_checkpoint(
            replicas, expected_policy=POLICY, expected_limits=LIMITS,
            expected_digest=receipt.digest,
        )
        self.assertTrue(result.degraded)
        self.assertEqual(result.acknowledged, ("slot-0", "slot-1"))
        self.assertEqual(result.unavailable, ("slot-2",))

    def test_corruption_does_not_trigger_implicit_slot_repair(self):
        replicas = slots()
        publish(scheduler(), replicas)
        replicas[0].data["digest"] = "0" * 64
        recover(replicas)
        self.assertEqual(replicas[0].data["digest"], "0" * 64)


class TestFileBackedCheckpointReplicas(unittest.TestCase):
    def make_replicas(self, directory):
        return [
            FileCheckpointReplica(
                f"slot-{i}", f"test-domain-{i}",
                Path(directory) / f"replica-{i}" / "checkpoint.json",
            )
            for i in range(3)
        ]

    def test_three_files_roundtrip_and_reload_without_object_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            for replica in replicas:
                replica.path.parent.mkdir()
            live = scheduler()
            receipt = publish(live, replicas)
            self.assertEqual(len(receipt.acknowledged), 3)
            reopened = self.make_replicas(folder)
            recovered = recover(reopened, expected_digest=receipt.digest)
            self.assertEqual(recovered.scheduler.snapshot(), live.snapshot())

    def test_deleted_primary_file_recovers_from_two_secondary_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            for replica in replicas:
                replica.path.parent.mkdir()
            publish(scheduler(), replicas)
            replicas[0].path.unlink()
            self.assertEqual(recover(replicas).matching, ("slot-1", "slot-2"))

    def test_truncated_file_is_rejected_and_other_two_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            for replica in replicas:
                replica.path.parent.mkdir()
            publish(scheduler(), replicas)
            replicas[1].path.write_bytes(b'{"schema":')
            self.assertEqual(recover(replicas).matching, ("slot-0", "slot-2"))

    def test_duplicate_json_key_is_rejected_even_when_json_parses(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            for replica in replicas:
                replica.path.parent.mkdir()
            publish(scheduler(), replicas)
            replicas[0].path.write_text('{"schema":"first","schema":"second"}')
            self.assertEqual(recover(replicas).matching, ("slot-1", "slot-2"))

    def test_file_adapter_rejects_oversized_checkpoint_read(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            for replica in replicas:
                replica.path.parent.mkdir()
            publish(scheduler(), replicas)
            with patch("skeleton.ai.model_runtime.admission_redundancy.MAX_CHECKPOINT_BYTES", 8):
                with self.assertRaisesRegex(ModelRuntimeError, "oversized"):
                    replicas[0].read()

    def test_file_adapter_rejects_oversized_checkpoint_write(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            replicas[0].path.parent.mkdir()
            with patch("skeleton.ai.model_runtime.admission_redundancy.MAX_CHECKPOINT_BYTES", 8):
                with self.assertRaisesRegex(ModelRuntimeError, "budget exceeded"):
                    replicas[0].write(scheduler().snapshot())

    def test_missing_provisioned_parent_fails_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            with self.assertRaisesRegex(ModelRuntimeError, "not provisioned"):
                replicas[0].write(scheduler().snapshot())
            self.assertFalse(replicas[0].path.parent.exists())

    def test_duplicate_file_path_rejected_even_with_different_domains(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            replicas[1] = FileCheckpointReplica(
                "different", "different-domain", replicas[0].path,
            )
            with self.assertRaisesRegex(ModelRuntimeError, "duplicate checkpoint storage path"):
                recover(replicas)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires no-follow file support")
    def test_symlink_replica_read_refuses_indirection(self):
        with tempfile.TemporaryDirectory() as folder:
            replicas = self.make_replicas(folder)
            for replica in replicas:
                replica.path.parent.mkdir()
            publish(scheduler(), replicas)
            replicas[0].path.unlink()
            replicas[0].path.symlink_to(replicas[1].path)
            self.assertEqual(recover(replicas).matching, ("slot-1", "slot-2"))


if __name__ == "__main__":
    unittest.main()
