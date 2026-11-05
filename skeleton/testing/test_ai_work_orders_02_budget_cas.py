"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class BudgetCases(QueueCase):
    def test_raises_on_unapproved_budget(self):
        with self.assertRaises(WorkOrderError):
            self.store.configure_budget("other",ceiling=500,operator_approved=False)
    def test_budget_can_decrease_only_above_reserved_plus_consumed(self):
        self.store.submit(self.order)
        self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        with self.assertRaises(WorkOrderError):
            self.store.configure_budget("local",ceiling=127,
                operator_approved=True,expected_revision=1)
        changed=self.store.configure_budget("local",ceiling=128,
            operator_approved=True,expected_revision=1)
        self.assertEqual(changed["revision"],2)
    def test_budget_version_conflict_denied(self):
        with self.assertRaises(WorkOrderError):
            self.store.configure_budget("local",ceiling=20000,
                operator_approved=True,expected_revision=5)
    def test_budget_requires_explicit_tenant_owner(self):
        with self.assertRaises(WorkOrderError):
            self.store.configure_budget("../../x",ceiling=10,operator_approved=True)

if __name__=="__main__":unittest.main()
