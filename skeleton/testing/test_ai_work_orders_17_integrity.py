"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class AuditCases(QueueCase):
    def test_full_chain_after_state_transitions(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        self.store.hold_unknown(self.order,expected_revision=3)
        report=self.store.audit()
        self.assertEqual(report["events"],4)
        self.assertEqual(report["jobs"],1)
    def test_audit_does_not_grant_model_release(self):
        self.store.submit(self.order)
        record=self.store.audit()
        self.assertFalse(record["native_inference_proved"])
        self.assertFalse(record["release_certified"])

if __name__=="__main__":unittest.main()
