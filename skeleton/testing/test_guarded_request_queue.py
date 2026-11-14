"""Live domain acceptance for queue; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.queue import FairQueue, QueueTicket
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestQueueGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'queue']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'queue']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_owner_round_robin(self):
        queue = FairQueue(capacity=4, per_owner=2)
        for owner, rid in (("a","a1"),("a","a2"),("b","b1")):
            queue.enqueue(QueueTicket(rid, owner))
        got = []
        while ticket := queue.poll():
            got.append(ticket.request_id)
            queue.finish(ticket)
        self.assertEqual(got, ["a1", "b1", "a2"])
    def test_no_inflight_cancellation(self):
        queue = FairQueue(capacity=1, per_owner=1)
        ticket = QueueTicket("r1", "tenant")
        queue.enqueue(ticket)
        self.assertEqual(queue.poll(), ticket)
        with self.assertRaises(GateDenied):
            queue.cancel("r1")
        queue.finish(ticket)
        self.assertFalse(queue.cancel("r1"))


if __name__ == '__main__':
    unittest.main()
