"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class ReplayConflictCases(QueueCase):
    def test_request_sha_reuse_different_seed_refused(self):
        self.store.submit(self.order)
        altered=self.other_order(seed=1,job_id=self.order.job_id)
        with self.assertRaises(WorkOrderError):
            self.store.submit(altered)
    def test_reconcile_wrong_prompt_does_not_touch_spine(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        with self.assertRaises(WorkOrderError):
            self.executor.reconcile(self.order,"substituted prompt")
        self.assertEqual(self.store.inspect(self.order)["status"],"dispatch-unknown")

if __name__=="__main__":unittest.main()
