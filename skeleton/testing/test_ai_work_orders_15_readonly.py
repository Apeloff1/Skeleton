"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class ReadonlyCases(QueueCase):
    def test_readonly_store_cannot_create_job(self):
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        self.store.submit(self.order)
        with WorkOrderStore(self.state_dir,readonly=True) as doctor:
            self.assertEqual(doctor.inspect(self.order)["status"],"queued")
            with self.assertRaises(WorkOrderError):doctor.submit(self.other_order(job_id="new",request_id="new"))
    def test_no_unknown_version_can_claim_compatibility(self):
        self.store.submit(self.order)
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        with WorkOrderStore(self.state_dir) as other:
            with other.db.transaction() as conn:
                conn.execute("UPDATE controls SET value='999' WHERE key='version'")
        with self.assertRaises(WorkOrderError):WorkOrderStore(self.state_dir)

if __name__=="__main__":unittest.main()
