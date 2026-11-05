"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class ModelBindingCases(QueueCase):
    def test_correct_worker_is_required(self):
        self.assertTrue(self.order.confirm_worker(self.worker))
    def test_changed_tokenizer_is_refused(self):
        self.worker.spine.backend.tokenizer_digest="c"*64
        with self.assertRaises(WorkOrderError):self.order.confirm_worker(self.worker)
    def test_changed_model_epoch_is_refused(self):
        self.worker.spine.identity.model_sha256="c"*64
        with self.assertRaises(WorkOrderError):self.order.confirm_worker(self.worker)

if __name__=="__main__":unittest.main()
