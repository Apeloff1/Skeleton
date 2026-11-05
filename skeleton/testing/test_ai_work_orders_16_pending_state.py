"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class PendingStateCases(QueueCase):
    def test_reconcile_does_not_regenerate_unknown_job(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        result=self.executor.reconcile(self.order,self.prompt)
        self.assertFalse(result["committed"])
        self.assertEqual(self.worker.generation_calls,0)
    def test_native_replay_can_reconcile_without_new_generation(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        self.worker.turn(self.order.session_id,self.order.request_id,self.prompt,
                         seed=self.order.seed,temperature=self.order.sampler_temperature)
        self.assertEqual(self.worker.generation_calls,1)
        result=self.executor.reconcile(self.order,self.prompt)
        self.assertTrue(result["recovered_from_spine"])
        self.assertEqual(self.worker.generation_calls,1)

if __name__=="__main__":unittest.main()
