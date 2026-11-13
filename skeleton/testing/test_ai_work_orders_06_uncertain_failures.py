"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class UnknownEffectCases(QueueCase):
    def test_backend_failure_remains_dispatch_unknown(self):
        self.store.submit(self.order)
        self.worker.turn=lambda *args,**kw:(_ for _ in ()).throw(RuntimeError("unknown native effects"))
        with self.assertRaises(RuntimeError):
            self.executor.run(self.order,self.prompt)
        self.assertEqual(self.store.inspect(self.order)["status"],"dispatch-unknown")
        self.assertGreater(self.store.budget("local")["reserved"],0)
        with self.assertRaises(WorkOrderError):
            self.executor.run(self.order,self.prompt)
    def test_no_replay_is_not_permission_to_retry(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        result=self.store.reconcile(self.order,self.worker,self.prompt)
        self.assertFalse(result["auto_retry"])
        self.assertEqual(result["status"],"dispatch-unknown")
        self.assertEqual(self.worker.generation_calls,0)
    def test_held_unknown_effect_retains_reservation(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        self.store.hold_unknown(self.order,expected_revision=3)
        self.assertEqual(self.store.inspect(self.order)["status"],"held")
        self.assertEqual(self.store.budget("local")["reserved"],128)

if __name__=="__main__":unittest.main()
