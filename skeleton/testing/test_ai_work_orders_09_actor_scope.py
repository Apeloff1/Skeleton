"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class TenantScopeCases(QueueCase):
    def test_second_subject_cannot_inspect_owner_job(self):
        self.store.submit(self.order)
        changed=self.other_order(subject="not_owner",job_id=self.order.job_id)
        with self.assertRaises(WorkOrderError):self.store.inspect(changed)
    def test_outbox_list_is_subject_scoped(self):
        self.store.submit(self.order)
        correct=self.store.pending_events(tenant="local",subject="owner",model_sha256="a"*64)
        wrong=self.store.pending_events(tenant="local",subject="other",model_sha256="a"*64)
        self.assertEqual(len(correct),1)
        self.assertEqual(wrong,())
    def test_changed_model_cannot_read_job(self):
        self.store.submit(self.order)
        with self.assertRaises(WorkOrderError):
            self.store.inspect(self.other_order(job_id=self.order.job_id,model_sha256="c"*64))

if __name__=="__main__":unittest.main()
