"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class OutboxCases(QueueCase):
    def test_ack_is_idempotent_and_integrity_kept(self):
        self.store.submit(self.order)
        first=self.store.pending_events(tenant="local",subject="owner",model_sha256="a"*64)
        self.assertEqual(len(first),1)
        sha=first[0]["event_sha256"]
        self.assertTrue(self.store.ack_event(sha,tenant="local",subject="owner",model_sha256="a"*64))
        self.assertFalse(self.store.ack_event(sha,tenant="local",subject="owner",model_sha256="a"*64))
        self.assertEqual(self.store.pending_events(tenant="local",subject="owner",model_sha256="a"*64),())
        self.assertEqual(self.store.audit()["events"],1)
    def test_cross_tenant_or_subject_ack_refused(self):
        self.store.submit(self.order)
        event=self.store.pending_events(tenant="local",subject="owner",model_sha256="a"*64)[0]
        with self.assertRaises(WorkOrderError):
            self.store.ack_event(event["event_sha256"],
                       tenant="local",subject="attacker",model_sha256="a"*64)

if __name__=="__main__":unittest.main()
