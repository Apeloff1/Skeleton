"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class RestartCases(QueueCase):
    def test_dispatch_unknown_survives_reopen(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.store.dispatch(self.order,lease["lease"],expected_revision=2)
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        self.store=WorkOrderStore(self.state_dir)
        self.assertEqual(self.store.inspect(self.order)["status"],"dispatch-unknown")
        self.assertEqual(self.store.budget("local")["reserved"],128)
    def test_committed_response_survives_reopen(self):
        self.store.submit(self.order)
        result=self.executor.run(self.order,self.prompt)
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        self.store=WorkOrderStore(self.state_dir)
        self.assertEqual(self.store.inspect(self.order)["output_sha"],result["output_sha256"])
        self.assertEqual(self.store.audit()["jobs"],1)

    def test_tampered_job_state_refused_on_cold_reopen(self):
        self.store.submit(self.order)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE jobs SET status='committed' WHERE job_id=?",
                         (self.order.job_id,))
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        with self.assertRaises(WorkOrderError):
            WorkOrderStore(self.state_dir)

    def test_tampered_event_payload_refused_on_cold_reopen(self):
        self.store.submit(self.order)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE events SET body=? WHERE sequence=1",
                         (b'{"forged":true}',))
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        with self.assertRaises(WorkOrderError):
            WorkOrderStore(self.state_dir)

    def test_tampered_quota_refused_on_cold_reopen(self):
        self.store.submit(self.order)
        lease=self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        self.assertEqual(lease["revision"],2)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE budgets SET reserved=reserved-1 WHERE tenant='local'")
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        with self.assertRaises(WorkOrderError):
            WorkOrderStore(self.state_dir)

if __name__=="__main__":unittest.main()
