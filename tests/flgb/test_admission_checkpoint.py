import copy
import unittest

from skeleton.ai.model_runtime.admission_checkpoint import restore_admission_scheduler
from skeleton.ai.model_runtime.admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


class TestAdmissionCheckpoint(unittest.TestCase):
    def build(self):
        scheduler = RuntimeAdmissionScheduler(
            AdmissionLimits(
                max_active_requests=2, max_queued_requests=4, max_batch_size=1,
                max_tokens_per_batch=100, kv_capacity_bytes=200, max_age_boost=10,
            ),
            policy=RuntimePolicyCompiler().compile(2024),
        )
        scheduler.submit(BatchRequest("active", 10, 5, 2), kv_bytes=60)
        scheduler.admit()
        scheduler.submit(BatchRequest("queued", 10, 5, 1), kv_bytes=40)
        return scheduler

    def test_snapshot_restore_round_trip_is_exact(self):
        original = self.build()
        restored = restore_admission_scheduler(original.snapshot())
        self.assertEqual(restored.snapshot(), original.snapshot())
        self.assertEqual(restored.active_ids, ("active",))
        self.assertEqual(restored.queued_ids, ("queued",))

    def test_restored_scheduler_replays_next_admission(self):
        original = self.build()
        restored = restore_admission_scheduler(original.snapshot())
        original.complete("active")
        restored.complete("active")
        self.assertEqual(original.admit(), restored.admit())

    def test_active_without_kv_fails_closed(self):
        snapshot = self.build().snapshot()
        snapshot["kv"] = []
        snapshot["capacity"]["kv_used_bytes"] = 0
        snapshot["capacity"]["kv_free_bytes"] = 200
        with self.assertRaisesRegex(ModelRuntimeError, "missing KV"):
            restore_admission_scheduler(snapshot)

    def test_capacity_tamper_fails_closed(self):
        snapshot = self.build().snapshot()
        snapshot["capacity"]["queued_tokens"] += 1
        with self.assertRaisesRegex(ModelRuntimeError, "capacity mismatch"):
            restore_admission_scheduler(snapshot)

    def test_duplicate_cross_state_identity_fails_closed(self):
        snapshot = self.build().snapshot()
        snapshot["queued"].append(copy.deepcopy(snapshot["active"][0]))
        with self.assertRaisesRegex(ModelRuntimeError, "queued and active"):
            restore_admission_scheduler(snapshot)


if __name__ == "__main__":
    unittest.main()
