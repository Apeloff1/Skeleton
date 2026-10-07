import unittest

from skeleton.ai.model_runtime.admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError


class TestRuntimeAdmissionScheduler(unittest.TestCase):
    def scheduler(self, **overrides):
        values = dict(
            max_active_requests=4,
            max_queued_requests=8,
            max_batch_size=2,
            max_tokens_per_batch=20,
            kv_capacity_bytes=100,
            max_age_boost=10,
        )
        values.update(overrides)
        return RuntimeAdmissionScheduler(AdmissionLimits(**values))

    def test_priority_then_fifo_is_deterministic(self):
        s = self.scheduler()
        s.submit(BatchRequest("low", 2, 2, priority=0), kv_bytes=10)
        s.submit(BatchRequest("high-a", 2, 2, priority=5), kv_bytes=10)
        s.submit(BatchRequest("high-b", 2, 2, priority=5), kv_bytes=10)
        d = s.admit()
        self.assertEqual(d.admitted, ("high-a", "high-b"))
        self.assertEqual(d.deferred, ("low",))
        self.assertEqual(s.active_ids, ("high-a", "high-b"))

    def test_token_budget_defers_without_dropping(self):
        s = self.scheduler(max_batch_size=3, max_tokens_per_batch=10)
        s.submit(BatchRequest("a", 3, 3), kv_bytes=10)
        s.submit(BatchRequest("b", 3, 3), kv_bytes=10)
        d = s.admit()
        self.assertEqual(d.admitted, ("a",))
        self.assertEqual(d.deferred, ("b",))
        self.assertEqual(s.queued_ids, ("b",))

    def test_kv_admission_evicts_old_inactive_entry(self):
        s = self.scheduler(kv_capacity_bytes=25, max_batch_size=1)
        s.submit(BatchRequest("old", 1, 1), kv_bytes=15)
        self.assertEqual(s.admit().admitted, ("old",))
        s.complete("old", retain_kv=True)
        s.submit(BatchRequest("new", 1, 1), kv_bytes=15)
        d = s.admit()
        self.assertEqual(d.admitted, ("new",))
        self.assertEqual(d.evicted_kv, ("old",))

    def test_active_kv_is_never_evicted(self):
        s = self.scheduler(kv_capacity_bytes=25, max_batch_size=1, max_active_requests=2)
        s.submit(BatchRequest("active", 1, 1), kv_bytes=15)
        self.assertEqual(s.admit().admitted, ("active",))
        s.submit(BatchRequest("waiting", 1, 1), kv_bytes=15)
        d = s.admit()
        self.assertEqual(d.admitted, ())
        self.assertEqual(d.deferred, ("waiting",))
        self.assertIn("waiting", s.queued_ids)

    def test_duplicate_and_oversized_work_fail_closed(self):
        s = self.scheduler()
        s.submit(BatchRequest("same", 1, 1), kv_bytes=10)
        with self.assertRaises(ModelRuntimeError):
            s.submit(BatchRequest("same", 1, 1), kv_bytes=10)
        with self.assertRaises(ModelRuntimeError):
            s.submit(BatchRequest("huge-kv", 1, 1), kv_bytes=101)
        with self.assertRaises(ModelRuntimeError):
            s.submit(BatchRequest("huge-token", 11, 10), kv_bytes=10)

    def test_snapshot_digest_is_replay_stable(self):
        def run():
            s = self.scheduler()
            s.submit(BatchRequest("a", 2, 3, priority=2), kv_bytes=11)
            s.submit(BatchRequest("b", 2, 2, priority=1), kv_bytes=12)
            return s.admit()
        left, right = run(), run()
        self.assertEqual(left, right)
        self.assertEqual(len(left.snapshot_digest), 64)

    def test_completion_releases_active_slot_and_kv(self):
        s = self.scheduler(max_batch_size=1)
        s.submit(BatchRequest("a", 1, 1), kv_bytes=20)
        s.submit(BatchRequest("b", 1, 1), kv_bytes=20)
        self.assertEqual(s.admit().admitted, ("a",))
        s.complete("a")
        self.assertEqual(s.admit().admitted, ("b",))
        self.assertNotIn("a", [e["request_id"] for e in s.snapshot()["kv"]])


if __name__ == "__main__":
    unittest.main()
