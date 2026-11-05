"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class DispatchCases(QueueCase):
    def test_dispatch_must_persist_before_native_call(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        dispatched=self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        self.assertEqual(dispatched["status"],"dispatch-unknown")
        self.assertEqual(self.store.inspect(self.order)["revision"],3)
        with self.assertRaises(WorkOrderError):
            self.store.dispatch(self.order,lease["lease"],expected_revision=2)
    def test_invalid_random_lease_cannot_dispatch(self):
        self.store.submit(self.order)
        self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        with self.assertRaises(WorkOrderError):
            self.store.dispatch(self.order,"b"*64,expected_revision=2)
        self.assertEqual(self.store.inspect(self.order)["status"],"leased")
    def test_queued_order_cannot_be_marked_native_committed(self):
        self.store.submit(self.order)
        with self.assertRaises(WorkOrderError):
            self.store.reconcile(self.order,self.worker,self.prompt)

if __name__=="__main__":unittest.main()
