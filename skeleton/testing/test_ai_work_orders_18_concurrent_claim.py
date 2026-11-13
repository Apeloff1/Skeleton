"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class ConcurrentClaimCases(QueueCase):
    def test_only_one_thread_wins_revision_one(self):
        import concurrent.futures
        self.store.submit(self.order)
        def admit(_):
            try:
                self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
                return True
            except WorkOrderError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(admit,range(2)))
        self.assertCountEqual(results,[True,False])
    def test_concurrent_budget_charge_cannot_exceed_ceiling(self):
        import concurrent.futures
        second=self.other_order(job_id="job2",session_id="session2",request_id="request2")
        self.store.submit(self.order)
        self.store.submit(second)
        self.store.configure_budget("local",ceiling=150,operator_approved=True,expected_revision=1)
        def admit(o):
            try:self.store.claim(o,expected_revision=1,reservation_tokens=128);return True
            except WorkOrderError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(admit,[self.order,second]))
        self.assertCountEqual(results,[True,False])

if __name__=="__main__":unittest.main()
