"""Deterministic admission recovery under interleaved operations.

Exercises the existing native scheduler, not a parallel simulation of it.
Snapshots must round-trip exactly at every state transition, and refused
operations may not partially mutate the queue, resident KV or sequence.
"""
from __future__ import annotations

import random
import unittest

from skeleton.ai.model_runtime.admission_checkpoint import restore_admission_scheduler
from skeleton.ai.model_runtime.admission_scheduler import (
    AdmissionLimits, RuntimeAdmissionScheduler,
)
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


LIMITS = AdmissionLimits(
    max_active_requests=3,
    max_queued_requests=6,
    max_batch_size=2,
    max_tokens_per_batch=24,
    kv_capacity_bytes=80,
    max_age_boost=7,
)


def replay_workload(seed: int, operations: int = 240) -> tuple[str, ...]:
    """Run repeatable bounded churn with a checkpoint after every operation."""
    rng = random.Random(seed)
    policy = RuntimePolicyCompiler().compile(2024)
    scheduler = RuntimeAdmissionScheduler(LIMITS, policy=policy)
    digests: list[str] = []
    serial = 0

    for step in range(operations):
        choice = rng.randrange(7)
        queued = scheduler.queued_ids
        active = scheduler.active_ids
        before = scheduler.snapshot()

        try:
            if choice == 0:
                name = f"req-{serial:04d}"
                serial += 1
                scheduler.submit(
                    BatchRequest(
                        name, rng.randint(0, 6), rng.randint(1, 4),
                        priority=rng.randint(-10, 10),
                    ),
                    kv_bytes=rng.randint(1, 25),
                    pinned_kv=bool(rng.getrandbits(1)),
                )
            elif choice == 1:
                scheduler.admit()
            elif choice == 2 and active:
                scheduler.complete(
                    rng.choice(active), retain_kv=bool(rng.getrandbits(1)),
                )
            elif choice == 3 and active:
                scheduler.retry(
                    rng.choice(active), priority_delta=rng.randint(-2, 2),
                )
            elif choice == 4 and (active or queued):
                scheduler.cancel(rng.choice(active + queued))
            elif choice == 5 and active:
                scheduler.set_kv_pinned(
                    rng.choice(active), bool(rng.getrandbits(1)),
                )
            else:
                scheduler.admit()
        except ModelRuntimeError:
            # Capacity and policy refusal must not damage a live scheduler.
            if choice in (0, 3):
                assert scheduler.snapshot() == before, (
                    f"non-atomic admission refusal at seed {seed}, step {step}"
                )
            else:
                raise

        snap = scheduler.snapshot()
        restored = restore_admission_scheduler(
            snap,
            expected_limits=LIMITS,
            expected_policy=policy,
            minimum_sequence=before["sequence"],
        )
        assert restored.snapshot() == snap, (
            f"checkpoint parity mismatch at seed {seed}, step {step}"
        )
        capacity = scheduler.capacity()
        assert capacity["queued_requests"] <= LIMITS.max_queued_requests
        assert capacity["active_requests"] <= LIMITS.max_active_requests
        assert 0 <= capacity["kv_used_bytes"] <= LIMITS.kv_capacity_bytes
        assert capacity["kv_free_bytes"] + capacity["kv_used_bytes"] == LIMITS.kv_capacity_bytes
        assert set(scheduler.active_ids).isdisjoint(scheduler.queued_ids)
        assert set(scheduler.queued_ids).isdisjoint(
            item["request_id"] for item in snap["kv"]
        )
        digests.append(snap["digest"])
    return tuple(digests)


class TestAdmissionCheckpointStateMachine(unittest.TestCase):
    def test_replay_stability_under_interleaved_operations(self):
        for seed in (0, 1, 17, 2026):
            with self.subTest(seed=seed):
                first = replay_workload(seed)
                self.assertEqual(first, replay_workload(seed))
                self.assertEqual(len(first), 240)

    def test_distinct_workloads_yield_distinct_trace_identities(self):
        self.assertNotEqual(
            replay_workload(1), replay_workload(2),
        )

    def test_active_pin_mutations_are_restoreable(self):
        scheduler = RuntimeAdmissionScheduler(LIMITS)
        scheduler.submit(BatchRequest("a", 1, 2), kv_bytes=20)
        scheduler.admit()
        for value in (True, False, True):
            scheduler.set_kv_pinned("a", value)
            checkpoint = scheduler.snapshot()
            restored = restore_admission_scheduler(checkpoint)
            self.assertEqual(restored.snapshot(), checkpoint)
            self.assertEqual(checkpoint["kv"][0]["pinned"], value)
            self.assertEqual(checkpoint["active"][0]["pinned_kv"], value)

    def test_retained_kv_eviction_roundtrip(self):
        scheduler = RuntimeAdmissionScheduler(
            AdmissionLimits(
                max_active_requests=2, max_queued_requests=2, max_batch_size=1,
                max_tokens_per_batch=10, kv_capacity_bytes=30, max_age_boost=10,
            )
        )
        scheduler.submit(BatchRequest("old", 1, 1), kv_bytes=20)
        self.assertEqual(scheduler.admit().admitted, ("old",))
        scheduler.complete("old", retain_kv=True)
        self.assertEqual(
            restore_admission_scheduler(scheduler.snapshot()).snapshot(),
            scheduler.snapshot(),
        )
        scheduler.submit(BatchRequest("new", 1, 1), kv_bytes=20)
        self.assertEqual(scheduler.admit().evicted_kv, ("old",))
        self.assertEqual(
            restore_admission_scheduler(scheduler.snapshot()).snapshot(),
            scheduler.snapshot(),
        )

    def test_pinned_retained_entry_is_never_evicted(self):
        scheduler = RuntimeAdmissionScheduler(
            AdmissionLimits(
                max_active_requests=2, max_queued_requests=2, max_batch_size=1,
                max_tokens_per_batch=10, kv_capacity_bytes=30, max_age_boost=10,
            )
        )
        scheduler.submit(BatchRequest("protected", 1, 1), kv_bytes=20, pinned_kv=True)
        scheduler.admit()
        scheduler.complete("protected", retain_kv=True)
        scheduler.submit(BatchRequest("incoming", 1, 1), kv_bytes=20)
        decision = scheduler.admit()
        self.assertEqual(decision.admitted, ())
        self.assertEqual(decision.deferred, ("incoming",))
        self.assertEqual(
            restore_admission_scheduler(scheduler.snapshot()).snapshot(),
            scheduler.snapshot(),
        )

    def test_kv_retained_identity_can_reenter_only_after_eviction(self):
        scheduler = RuntimeAdmissionScheduler(
            AdmissionLimits(
                max_active_requests=2, max_queued_requests=2, max_batch_size=1,
                max_tokens_per_batch=10, kv_capacity_bytes=30, max_age_boost=10,
            )
        )
        scheduler.submit(BatchRequest("old", 1, 1), kv_bytes=20)
        scheduler.admit()
        scheduler.complete("old", retain_kv=True)
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate"):
            scheduler.submit(BatchRequest("old", 1, 1), kv_bytes=1)
        scheduler.submit(BatchRequest("replacement", 1, 1), kv_bytes=20)
        self.assertEqual(scheduler.admit().evicted_kv, ("old",))
        scheduler.complete("replacement")
        scheduler.submit(BatchRequest("old", 1, 1), kv_bytes=1)
        self.assertEqual(scheduler.admit().admitted, ("old",))

    def test_empty_admission_is_deterministic_and_restoreable(self):
        a, b = RuntimeAdmissionScheduler(LIMITS), RuntimeAdmissionScheduler(LIMITS)
        for _ in range(10):
            self.assertEqual(a.admit(), b.admit())
            self.assertEqual(
                restore_admission_scheduler(a.snapshot()).snapshot(),
                a.snapshot(),
            )

    def test_queue_pressure_does_not_modify_active_state(self):
        limits = AdmissionLimits(
            max_active_requests=2, max_queued_requests=1, max_batch_size=1,
            max_tokens_per_batch=10, kv_capacity_bytes=30, max_age_boost=10,
        )
        scheduler = RuntimeAdmissionScheduler(limits)
        scheduler.submit(BatchRequest("active", 1, 1), kv_bytes=10)
        scheduler.admit()
        scheduler.submit(BatchRequest("waiting", 1, 1), kv_bytes=10)
        before = scheduler.snapshot()
        for _ in range(10):
            with self.assertRaisesRegex(ModelRuntimeError, "retry queue capacity"):
                scheduler.retry("active")
            self.assertEqual(scheduler.snapshot(), before)
        scheduler.complete("active")
        self.assertEqual(
            restore_admission_scheduler(scheduler.snapshot()).snapshot(),
            scheduler.snapshot(),
        )


if __name__ == "__main__":
    unittest.main()
