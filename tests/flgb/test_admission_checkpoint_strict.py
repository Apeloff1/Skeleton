"""Strict admission scheduler checkpoint restore and adversarial replay."""
from __future__ import annotations

import copy
import unittest

from skeleton.ai.model_runtime.admission_checkpoint import restore_admission_scheduler
from skeleton.ai.model_runtime.admission_scheduler import (
    AdmissionLimits, RuntimeAdmissionScheduler, _digest,
)
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


class TestStrictSchedulerRestore(unittest.TestCase):
    def build(self):
        limits = AdmissionLimits(
            max_active_requests=3, max_queued_requests=4, max_batch_size=1,
            max_tokens_per_batch=50, kv_capacity_bytes=200, max_age_boost=10,
        )
        policy = RuntimePolicyCompiler().compile(2024)
        scheduler = RuntimeAdmissionScheduler(limits, policy=policy)
        scheduler.submit(BatchRequest("active", 10, 5), kv_bytes=50, pinned_kv=True)
        self.assertEqual(scheduler.admit().admitted, ("active",))
        scheduler.submit(BatchRequest("queued", 10, 5), kv_bytes=35)
        return scheduler

    @staticmethod
    def sign(snapshot):
        snapshot["digest"] = _digest({k: v for k, v in snapshot.items() if k != "digest"})
        return snapshot

    def test_canonical_roundtrip_with_trusted_deployment_pins(self):
        scheduler = self.build()
        snap = scheduler.snapshot()
        restored = restore_admission_scheduler(
            snap, expected_policy=scheduler.policy,
            expected_limits=scheduler.limits,
            minimum_sequence=snap["sequence"],
            expected_digest=snap["digest"],
        )
        self.assertEqual(restored.snapshot(), snap)
        self.assertEqual(restored.active_ids, ("active",))
        self.assertEqual(restored.queued_ids, ("queued",))

    def test_empty_snapshot_and_retained_kv_roundtrip(self):
        empty = RuntimeAdmissionScheduler()
        self.assertEqual(
            restore_admission_scheduler(empty.snapshot()).snapshot(),
            empty.snapshot(),
        )
        scheduler = self.build()
        scheduler.complete("active", retain_kv=True)
        restored = restore_admission_scheduler(scheduler.snapshot())
        self.assertEqual(restored.snapshot(), scheduler.snapshot())

    def test_noncanonical_collections_rejected_even_with_recomputed_checksum(self):
        scheduler = self.build()
        scheduler.submit(BatchRequest("zz", 1, 1), kv_bytes=10)
        snap = scheduler.snapshot()
        snap["queued"].reverse()
        with self.assertRaisesRegex(ModelRuntimeError, "noncanonical"):
            restore_admission_scheduler(self.sign(snap))

    def test_bad_checksum_and_expected_revision_denied(self):
        snap = self.build().snapshot()
        with self.assertRaisesRegex(ModelRuntimeError, "digest mismatch"):
            restore_admission_scheduler(snap | {"sequence": 123})
        with self.assertRaisesRegex(ModelRuntimeError, "expected digest"):
            restore_admission_scheduler(snap, expected_digest="0" * 64)

    def test_minimum_sequence_rollback_fence(self):
        snap = self.build().snapshot()
        with self.assertRaisesRegex(ModelRuntimeError, "minimum sequence"):
            restore_admission_scheduler(snap, minimum_sequence=snap["sequence"] + 1)
        self.assertEqual(
            restore_admission_scheduler(snap, minimum_sequence=0).snapshot(), snap
        )
        with self.assertRaises(ModelRuntimeError):
            restore_admission_scheduler(snap, minimum_sequence=True)

    def test_trusted_policy_and_limit_pins(self):
        scheduler = self.build()
        snap = scheduler.snapshot()
        wrong_policy = RuntimePolicyCompiler().compile(2020)
        with self.assertRaisesRegex(ModelRuntimeError, "policy mismatch"):
            restore_admission_scheduler(snap, expected_policy=wrong_policy)
        with self.assertRaisesRegex(ModelRuntimeError, "limits mismatch"):
            restore_admission_scheduler(snap, expected_limits=AdmissionLimits())
        with self.assertRaises(ModelRuntimeError):
            restore_admission_scheduler(snap, expected_limits=object())
        with self.assertRaises(ModelRuntimeError):
            restore_admission_scheduler(snap, expected_policy=object())

    def test_unknown_or_missing_top_level_keys(self):
        snap = self.build().snapshot()
        for changed in (
            snap | {"unknown": "data"},
            {k: v for k, v in snap.items() if k != "policy"},
        ):
            with self.assertRaisesRegex(ModelRuntimeError, "fields"):
                restore_admission_scheduler(self.sign(changed))

    def test_valid_digest_does_not_allow_coercing_request_fields(self):
        for key, replacement in (
            ("request_id", 123),
            ("prompt_tokens", "10"),
            ("max_new_tokens", True),
            ("priority", 1.0),
            ("kv_bytes", "50"),
            ("enqueue_sequence", "0"),
            ("pinned_kv", 1),
        ):
            with self.subTest(field=key), self.assertRaises(ModelRuntimeError):
                snap = self.build().snapshot()
                snap["active"][0][key] = replacement
                restore_admission_scheduler(self.sign(snap))

    def test_valid_digest_does_not_allow_coercing_kv_fields(self):
        for key, replacement in (
            ("request_id", 999),
            ("bytes", True),
            ("last_used_sequence", "1"),
            ("pinned", 1),
        ):
            with self.subTest(field=key), self.assertRaises(ModelRuntimeError):
                snap = self.build().snapshot()
                snap["kv"][0][key] = replacement
                restore_admission_scheduler(self.sign(snap))

    def test_invalid_limit_and_capacity_types(self):
        for key, replacement in (
            ("max_active_requests", True),
            ("max_batch_size", 1.5),
            ("max_tokens_per_batch", "50"),
        ):
            with self.subTest(field=key), self.assertRaises(ModelRuntimeError):
                snap = self.build().snapshot()
                snap["limits"][key] = replacement
                restore_admission_scheduler(self.sign(snap))
        for value in (True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(ModelRuntimeError):
                snap = self.build().snapshot()
                snap["capacity"]["active_requests"] = value
                restore_admission_scheduler(self.sign(snap))

    def test_active_kv_bytes_or_pin_mismatch(self):
        for key, value in (("bytes", 49), ("pinned", False)):
            with self.subTest(field=key), self.assertRaisesRegex(ModelRuntimeError, "mismatch"):
                snap = self.build().snapshot()
                snap["kv"][0][key] = value
                restore_admission_scheduler(self.sign(snap))

    def test_enqueued_or_resident_sequence_cannot_advance_into_future(self):
        for collection, key in (
            ("queued", "enqueue_sequence"),
            ("active", "enqueue_sequence"),
            ("kv", "last_used_sequence"),
        ):
            with self.subTest(collection=collection), self.assertRaisesRegex(
                ModelRuntimeError, "future"
            ):
                snap = self.build().snapshot()
                snap[collection][0][key] = snap["sequence"]
                restore_admission_scheduler(self.sign(snap))

    def test_duplicate_enqueue_sequence_even_with_unique_ids(self):
        snap = self.build().snapshot()
        snap["queued"][0]["enqueue_sequence"] = snap["active"][0]["enqueue_sequence"]
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate"):
            restore_admission_scheduler(self.sign(snap))

    def test_queued_resident_kv_identity_is_not_allowed(self):
        snap = self.build().snapshot()
        snap["kv"][0]["request_id"] = "queued"
        with self.assertRaises(ModelRuntimeError):
            restore_admission_scheduler(self.sign(snap))

    def test_valid_digest_does_not_allow_policy_shape_or_identity_coercion(self):
        for key, value in (
            ("through_year", "2024"),
            ("digest", "0" * 63),
            ("capabilities", ["x", "x"]),
            ("experimental", ["x", True]),
        ):
            with self.subTest(field=key), self.assertRaises(ModelRuntimeError):
                snap = self.build().snapshot()
                snap["policy"][key] = value
                restore_admission_scheduler(self.sign(snap))

    def test_duplicate_kv_identity_and_duplicate_queue_id(self):
        for collection in ("kv", "queued"):
            snap = self.build().snapshot()
            snap[collection].append(copy.deepcopy(snap[collection][0]))
            with self.subTest(collection=collection), self.assertRaises(ModelRuntimeError):
                restore_admission_scheduler(self.sign(snap))

    def test_restored_scheduler_continues_deterministic_admission(self):
        original = self.build()
        restored = restore_admission_scheduler(original.snapshot())
        original.complete("active")
        restored.complete("active")
        self.assertEqual(original.admit(), restored.admit())
        self.assertEqual(original.snapshot(), restored.snapshot())


class TestRetainedKVIdentitySafety(unittest.TestCase):
    def test_resident_identity_cannot_be_resubmitted(self):
        scheduler = RuntimeAdmissionScheduler()
        scheduler.submit(BatchRequest("retained", 1, 1), kv_bytes=20)
        self.assertEqual(scheduler.admit().admitted, ("retained",))
        scheduler.complete("retained", retain_kv=True)
        before = scheduler.snapshot()
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate"):
            scheduler.submit(BatchRequest("retained", 1, 1), kv_bytes=20)
        self.assertEqual(scheduler.snapshot(), before)

    def test_submit_requires_batch_request(self):
        scheduler = RuntimeAdmissionScheduler()
        with self.assertRaisesRegex(ModelRuntimeError, "BatchRequest"):
            scheduler.submit(object(), kv_bytes=10)
        self.assertEqual(scheduler.queued_ids, ())

    def test_retry_at_full_queue_preserves_active_kv_and_sequence(self):
        limits = AdmissionLimits(
            max_active_requests=2, max_queued_requests=1, max_batch_size=1,
            max_tokens_per_batch=10, kv_capacity_bytes=100, max_age_boost=10,
        )
        scheduler = RuntimeAdmissionScheduler(limits)
        scheduler.submit(BatchRequest("active", 1, 1), kv_bytes=20)
        scheduler.admit()
        scheduler.submit(BatchRequest("queued", 1, 1), kv_bytes=20)
        before = scheduler.snapshot()
        with self.assertRaisesRegex(ModelRuntimeError, "retry queue capacity"):
            scheduler.retry("active")
        self.assertEqual(before, scheduler.snapshot())
        self.assertEqual(
            restore_admission_scheduler(scheduler.snapshot()).snapshot(), before
        )
        scheduler.cancel("queued")
        scheduler.retry("active")
        self.assertEqual(scheduler.active_ids, ())
        self.assertEqual(scheduler.queued_ids, ("active",))
        self.assertEqual(scheduler.capacity()["kv_used_bytes"], 0)

    def test_invalid_retry_delta_is_atomic(self):
        scheduler = self.build()
        before = scheduler.snapshot()
        for delta in (True, 1.5, 1_000_001):
            with self.subTest(delta=delta), self.assertRaises(ModelRuntimeError):
                scheduler.retry("active", priority_delta=delta)
            self.assertEqual(scheduler.snapshot(), before)

    def test_constructor_rejects_invalid_limits(self):
        with self.assertRaisesRegex(ModelRuntimeError, "AdmissionLimits"):
            RuntimeAdmissionScheduler(limits={})
        with self.assertRaisesRegex(ModelRuntimeError, "AdmissionLimits"):
            RuntimeAdmissionScheduler(limits=False)


if __name__ == "__main__":
    unittest.main()
