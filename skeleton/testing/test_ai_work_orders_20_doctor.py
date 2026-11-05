"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class DoctorCases(QueueCase):
    def test_doctor_reports_real_work_queue_holds(self):
        from skeleton.ai.runtime.operational_ai.work_orders.doctor import inspect
        self.store.submit(self.order)
        view=inspect(self.store,tenant="local",subject="owner",model_sha256="a"*64)
        self.assertEqual(view["observed_jobs"],1)
        self.assertFalse(view["release_certified"])
    def test_list_is_bounded_and_actor_scoped(self):
        self.store.submit(self.order)
        rows=self.store.list_jobs(tenant="local",subject="owner",model_sha256="a"*64)
        self.assertEqual(len(rows),1)
        self.assertEqual(self.store.list_jobs(tenant="other",subject="owner",model_sha256="a"*64),())
        with self.assertRaises(WorkOrderError):
            self.store.list_jobs(tenant="local",subject="owner",model_sha256="a"*64,limit=10000)

if __name__=="__main__":unittest.main()
