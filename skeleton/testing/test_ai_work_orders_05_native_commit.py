"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class CommitCases(QueueCase):
    def test_real_interface_turn_commits_only_after_spine_replay(self):
        self.store.submit(self.order)
        result=self.executor.run(self.order,self.prompt)
        self.assertEqual(result["status"],"committed")
        self.assertTrue(result["recovered_from_spine"])
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(self.store.budget("local")["reserved"],0)
        self.assertGreater(self.store.budget("local")["consumed"],0)
        with self.assertRaises(WorkOrderError):
            self.executor.run(self.order,self.prompt)
    def test_no_native_call_when_prompt_hash_is_different(self):
        self.store.submit(self.order)
        with self.assertRaises(WorkOrderError):
            self.executor.run(self.order,"wrong")
        self.assertEqual(self.worker.generation_calls,0)
    def test_tampered_result_is_not_considered_success(self):
        self.store.submit(self.order)
        self.worker.spine.replay=lambda *args,**kw:{"replayed":True,
            "model_sha256":"a"*64,"tokenizer_sha256":"b"*64,
            "text":"tampered","output_sha256":"c"*64,
            "prompt_tokens":2,"generated_tokens":1}
        result=self.executor.run if False else None
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        with self.assertRaises(Exception):
            self.store.reconcile(self.order,self.worker,self.prompt)
        self.assertEqual(self.store.inspect(self.order)["status"],"dispatch-unknown")

if __name__=="__main__":unittest.main()
