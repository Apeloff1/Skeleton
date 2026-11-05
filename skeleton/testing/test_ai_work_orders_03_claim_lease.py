"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class LeaseCases(QueueCase):
    def test_claim_uses_random_secret_and_cas(self):
        self.store.submit(self.order)
        receipt=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.assertEqual(len(receipt["lease"]),64)
        self.assertEqual(self.store.inspect(self.order)["revision"],2)
        with self.assertRaises(WorkOrderError):
            self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
    def test_tenant_capacity_reservation_atomic(self):
        self.store.submit(self.order)
        self.store.claim(self.order,expected_revision=1,reservation_tokens=5000)
        self.assertEqual(self.store.budget("local")["reserved"],5000)
        with self.assertRaises(WorkOrderError):
            self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
    def test_small_reservation_fails_without_side_effect(self):
        self.store.submit(self.order)
        with self.assertRaises(WorkOrderError):
            self.store.claim(self.order,expected_revision=1,reservation_tokens=2)
        self.assertEqual(self.store.budget("local")["reserved"],0)

if __name__=="__main__":unittest.main()
