"""Strict JSON, bounds and deterministic policy-denial contracts."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.canonical import (
    encode, decode, fingerprint, require_int,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.deadline import Deadline
from skeleton.ai.runtime.operational_ai.durable_jobs.state_rules import (
    authorize_transition, must_hold_on_unknown_outcome,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.backoff import ManualRetrySchedule
from skeleton.ai.runtime.operational_ai.durable_jobs.spec import (
    JobIdentity,JobSpec,WorkLimits,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied


class TestDurableContracts(unittest.TestCase):
    def test_canonical_order_stable(self):
        self.assertEqual(fingerprint({"b":2,"a":1}),fingerprint({"a":1,"b":2}))

    def test_duplicate_map_keys_denied(self):
        with self.assertRaises(JobDenied):
            decode(b'{"a":1,"a":2}')

    def test_nonfinite_input_denied(self):
        with self.assertRaises(JobDenied):
            decode(b'{"x":NaN}')
        with self.assertRaises(JobDenied):
            encode({"x":float("inf")})

    def test_boolean_integer_boundary(self):
        with self.assertRaises(JobDenied):
            require_int(True,0,10,"clock")

    def test_deadline_parent_fence(self):
        deadline=Deadline(1000,10000)
        self.assertEqual(deadline.remaining(2000),8000)
        self.assertEqual(deadline.child(now_ms=2000,duration_ms=20000).expires_ms,10000)
        with self.assertRaises(JobDenied):
            deadline.require_active(10000)

    def test_unknown_generation_outcome_must_hold(self):
        self.assertTrue(must_hold_on_unknown_outcome(
            generation_started=True,authoritative_commit_known=False))
        self.assertFalse(must_hold_on_unknown_outcome(
            generation_started=False,authoritative_commit_known=False))

    def test_terminal_states_cannot_be_reopened(self):
        for state in ("completed","cancelled","failed"):
            with self.subTest(state=state), self.assertRaises(JobDenied):
                authorize_transition(state,"pending",operator=True)

    def test_manual_retry_requires_verification(self):
        schedule=ManualRetrySchedule()
        with self.assertRaises(JobDenied):
            schedule.next_delay(1,operator_approved=True,
                                authoritative_no_commit_proved=False)
        self.assertEqual(schedule.next_delay(
            3,operator_approved=True,authoritative_no_commit_proved=True),4000)


if __name__=="__main__":
    unittest.main()
