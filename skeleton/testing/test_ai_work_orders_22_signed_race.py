"""Atomic signed admission must serialize a reused HMAC token across threads."""
import concurrent.futures
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.authorization import OperatorAuthority
from skeleton.ai.runtime.operational_ai.work_orders.ingress import SignedIngress
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError
class SignedRaceTests(QueueCase):
    def test_concurrent_same_ticket_only_one_job_exists(self):
        signer=OperatorAuthority(b"S"*32)
        token=signer.issue(self.order,issued_at=100,expires_at=200,approved=True)
        ingress=SignedIngress(self.store,signer)
        def submit(_):
            try:ingress.submit(self.order,token,observed_at=150);return "accepted"
            except WorkOrderError:return "rejected"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(submit,[1,2]))
        self.assertCountEqual(outcomes,["accepted","rejected"])
        self.assertEqual(self.store.audit()["jobs"],1)
if __name__=="__main__":unittest.main()
