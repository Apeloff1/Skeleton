"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class SubmitCases(QueueCase):
    def test_same_identity_is_idempotent(self):
        self.assertTrue(self.store.submit(self.order)["created"])
        self.assertFalse(self.store.submit(self.order)["created"])
        self.assertEqual(self.store.inspect(self.order)["revision"],1)
        self.assertEqual(self.store.audit()["jobs"],1)
    def test_same_id_with_changed_prompt_refused(self):
        self.store.submit(self.order)
        other=self.other_order(prompt_text="different",job_id=self.order.job_id)
        with self.assertRaises(WorkOrderError):self.store.submit(other)
    def test_model_epoch_mismatch_refused_even_if_job_id_same(self):
        self.store.submit(self.order)
        other=self.other_order(model_sha256="c"*64,job_id=self.order.job_id)
        with self.assertRaises(WorkOrderError):self.store.submit(other)
    def test_duplicate_request_under_alternate_job_id_refused(self):
        self.store.submit(self.order)
        other=self.other_order(job_id="second")
        with self.assertRaises(Exception):self.store.submit(other)

if __name__=="__main__":unittest.main()
