"""Native traffic admission concurrency, fairness and no-speculative-retry holds.

These are host scheduler source tests. Real inference execution and crash
recovery remain owned by the canonical SQLite execution spine.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import threading
import unittest

from skeleton.jeeves.native_fabric.contracts import ContractHold
from skeleton.jeeves.native_fabric.traffic import (
    TrafficRequest, TrafficTicket, TrafficHold, FairTrafficQueue,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def request(n, *, cohort="a", scope=SHA_A, priority=0,
            created_ns=1_000_000_000, deadline_ns=2_000_000_000):
    return TrafficRequest(
        request_id=f"native_request_{n}",
        scope_sha256=scope, prompt_sha256=SHA_B,
        session_id=f"native_session_{n}",
        output_token_ceiling=128, priority=priority,
        created_ns=created_ns, deadline_ns=deadline_ns,
        cohort=cohort,
    )


class TestNativeTrafficScheduler(unittest.TestCase):
    def setUp(self):
        self.now = [1_100_000_000]
        self.queue = FairTrafficQueue(
            maximum_pending=100, maximum_active=4,
            maximum_per_scope=2, clock_ns=lambda: self.now[0],
        )

    def test_admit_claim_and_commit_authoritative_receipt(self):
        self.queue.submit(request(1))
        claimed = self.queue.claim_next()
        self.assertEqual(claimed.state, "claimed")
        settled = self.queue.commit(
            claimed.request.request_id, authoritative_receipt_sha256=SHA_C,
        )
        self.assertEqual(settled.state, "committed")
        self.assertEqual(settled.committed_receipt_sha256, SHA_C)
        self.assertEqual(self.queue.snapshot()["active_slots"], 0)

    def test_duplicate_request_id_is_never_second_execution_grant(self):
        self.queue.submit(request(1))
        with self.assertRaises(TrafficHold):
            self.queue.submit(request(1))

    def test_repeated_claim_after_claim_does_not_double_allocate(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        self.assertIsNone(self.queue.claim_next())

    def test_committed_ticket_cannot_claim_again(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        self.queue.commit("native_request_1", authoritative_receipt_sha256=SHA_C)
        self.assertIsNone(self.queue.claim_next())

    def test_high_priority_work_wins_within_same_cohort(self):
        self.queue.submit(request(1, priority=1))
        self.queue.submit(request(2, priority=5))
        self.assertEqual(self.queue.claim_next().request.request_id, "native_request_2")

    def test_equal_priority_preserves_submission_order(self):
        self.queue.submit(request(1))
        self.queue.submit(request(2))
        self.assertEqual(self.queue.claim_next().request.request_id, "native_request_1")

    def test_cohorts_rotate_fairly_across_multiple_scopes(self):
        q = FairTrafficQueue(
            maximum_active=4, maximum_per_scope=4,
            clock_ns=lambda: self.now[0],
        )
        q.submit(request(1, cohort="a"))
        q.submit(request(2, cohort="b", scope=SHA_B))
        q.submit(request(3, cohort="a"))
        q.submit(request(4, cohort="b", scope=SHA_B))
        actual = [q.claim_next().request.request_id for _ in range(4)]
        self.assertEqual(actual, [
            "native_request_1", "native_request_2",
            "native_request_3", "native_request_4",
        ])

    def test_per_scope_quota_is_enforced(self):
        q = FairTrafficQueue(
            maximum_active=8, maximum_per_scope=1,
            clock_ns=lambda: self.now[0],
        )
        q.submit(request(1))
        q.submit(request(2))
        q.submit(request(3, scope=SHA_B))
        self.assertEqual(q.claim_next().request.request_id, "native_request_1")
        self.assertEqual(q.claim_next().request.request_id, "native_request_3")
        self.assertIsNone(q.claim_next())

    def test_global_active_ceiling_is_not_oversubscribed(self):
        q = FairTrafficQueue(
            maximum_active=1, maximum_per_scope=3,
            clock_ns=lambda: self.now[0],
        )
        q.submit(request(1))
        q.submit(request(2))
        q.claim_next()
        self.assertIsNone(q.claim_next())
        self.assertEqual(q.snapshot()["active_slots"], 1)

    def test_failed_or_uncertain_model_remains_held_without_retry(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        held = self.queue.hold("native_request_1", code="unknown_native_effect")
        self.assertEqual(held.state, "held")
        self.assertEqual(self.queue.snapshot()["active_slots"], 1)
        with self.assertRaises(TrafficHold):
            self.queue.commit("native_request_1", authoritative_receipt_sha256=SHA_C)
        with self.assertRaises(TrafficHold):
            self.queue.submit(request(1))

    def test_claimed_request_expiry_marks_unknown_and_retains_slot(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        self.now[0] = 2_000_000_000
        status = self.queue.snapshot()
        self.assertEqual(status["counts"]["held"], 1)
        self.assertEqual(status["active_slots"], 1)
        self.assertEqual(self.queue.inspect("native_request_1").hold_code,
                         "unknown_native_effect")

    def test_unclaimed_expiry_can_be_cancelled_without_native_effect(self):
        self.queue.submit(request(1))
        self.now[0] = 2_000_000_000
        self.queue.snapshot()
        ticket = self.queue.inspect("native_request_1")
        self.assertEqual(ticket.state, "cancelled")
        self.assertEqual(ticket.hold_code, "admission_expired")
        self.assertEqual(self.queue.snapshot()["active_slots"], 0)

    def test_operator_can_cancel_before_claim_only(self):
        self.queue.submit(request(1))
        stopped = self.queue.cancel_before_claim("native_request_1")
        self.assertEqual(stopped.state, "cancelled")
        self.assertIsNone(self.queue.claim_next())

    def test_operator_cannot_cancel_claimed_native_work(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        with self.assertRaises(TrafficHold):
            self.queue.cancel_before_claim("native_request_1")

    def test_commit_cannot_be_accepted_without_authoritative_sha256(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        for value in (None, "", "not_sha", SHA_C.upper()):
            with self.subTest(value=value), self.assertRaises(Exception):
                self.queue.commit(
                    "native_request_1", authoritative_receipt_sha256=value,
                )
        self.assertEqual(self.queue.inspect("native_request_1").state, "claimed")

    def test_commit_after_deadline_is_rejected_and_remains_held(self):
        self.queue.submit(request(1))
        self.queue.claim_next()
        self.now[0] = 2_100_000_000
        with self.assertRaises(TrafficHold):
            self.queue.commit("native_request_1", authoritative_receipt_sha256=SHA_C)
        self.assertEqual(self.queue.inspect("native_request_1").state, "held")

    def test_queue_capacity_is_a_hard_bound(self):
        q = FairTrafficQueue(
            maximum_pending=1, clock_ns=lambda: self.now[0],
        )
        q.submit(request(1))
        with self.assertRaises(TrafficHold):
            q.submit(request(2))

    def test_cohort_inventory_is_finite(self):
        q = FairTrafficQueue(
            maximum_cohorts=1, clock_ns=lambda: self.now[0],
        )
        q.submit(request(1, cohort="a"))
        with self.assertRaises(TrafficHold):
            q.submit(request(2, cohort="b"))

    def test_status_never_claims_restart_or_release_qualification(self):
        self.queue.submit(request(1))
        snapshot = self.queue.snapshot()
        self.assertFalse(snapshot["durable_restart_qualified"])
        self.assertFalse(snapshot["native_effects_reconciled"])
        self.assertFalse(snapshot["release_certified"])

    def test_unbounded_output_tokens_or_deadlines_denied(self):
        for value in (0, -1, True, 9000):
            with self.subTest(value=value), self.assertRaises(ContractHold):
                replace(request(1), output_token_ceiling=value)
        with self.assertRaises(ContractHold):
            replace(request(1), deadline_ns=0)

    def test_cohort_no_dangling_claims_after_queued_cancellation(self):
        self.queue.submit(request(1, cohort="a"))
        self.queue.cancel_before_claim("native_request_1")
        self.queue.submit(request(2, cohort="a"))
        self.assertEqual(self.queue.claim_next().request.request_id, "native_request_2")

    def test_occupied_scope_can_be_skipped_for_another_ready_scope(self):
        q = FairTrafficQueue(
            maximum_active=2, maximum_per_scope=1,
            clock_ns=lambda: self.now[0],
        )
        q.submit(request(1, scope=SHA_A, priority=10))
        q.submit(request(2, scope=SHA_A, priority=9))
        q.submit(request(3, scope=SHA_B, priority=1))
        q.claim_next()
        self.assertEqual(q.claim_next().request.request_id, "native_request_3")

    def test_concurrent_submission_is_serialized_and_unique(self):
        q = FairTrafficQueue(
            maximum_pending=500, clock_ns=lambda: self.now[0],
        )
        errors = []
        def submit(n):
            try:
                q.submit(request(n, scope=SHA_A if n%2 else SHA_B))
            except Exception as exc:
                errors.append(type(exc).__name__)
        threads = [threading.Thread(target=submit, args=(i,)) for i in range(64)]
        for worker in threads:
            worker.start()
        for worker in threads:
            worker.join()
        self.assertEqual(errors, [])
        self.assertEqual(q.snapshot()["counts"]["queued"], 64)

    def test_cancelled_request_id_is_not_reusable(self):
        self.queue.submit(request(1))
        self.queue.cancel_before_claim("native_request_1")
        with self.assertRaises(TrafficHold):
            self.queue.submit(request(1))


if __name__ == "__main__":
    unittest.main()
