"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class CancelCases(QueueCase):
    def test_cancel_before_dispatch_returns_only_proven_unused_reservation(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        response=self.store.abandon_before_dispatch(self.order,lease["lease"],
                       expected_revision=2,operator_approved=True)
        self.assertTrue(response["reservation_released"])
        self.assertEqual(self.store.budget("local")["reserved"],0)
    def test_unapproved_cancel_rejected(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        with self.assertRaises(WorkOrderError):
            self.store.abandon_before_dispatch(self.order,lease["lease"],
                         expected_revision=2,operator_approved=False)
    def test_dispatch_fence_disables_cancel_refund(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        with self.assertRaises(WorkOrderError):
            self.store.abandon_before_dispatch(self.order,lease["lease"],
                expected_revision=3,operator_approved=True)

if __name__=="__main__":unittest.main()
