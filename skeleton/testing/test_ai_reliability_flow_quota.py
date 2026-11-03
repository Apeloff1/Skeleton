"""Focused operational AI reliability test: quota. No synthetic native E2E claim."""
import concurrent.futures
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.quota import Quota
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class QuotaTests(unittest.TestCase):
    def test_concurrent_tenant_reservations_cannot_overspend(self):
        book=Quota(tenant_ceiling=10,global_ceiling=20)
        def reserve(request):
            try:book.reserve("tenant",request,prompt=7,output=3);return "admitted"
            except Rejected:return "held"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(reserve,["r1","r2"]))
        self.assertCountEqual(result,["admitted","held"])
    def test_failed_commit_cannot_refund_unknown_effects(self):
        book=Quota(tenant_ceiling=20,global_ceiling=20)
        book.reserve("t","r1",prompt=10,output=5)
        with self.assertRaises(Rejected):
            book.release_without_effect("t","r1",effect_absent=False)
        self.assertEqual(book.commit("t","r1",prompt=8,output=2)["charged_tokens"],10)
    def test_double_charge_and_overcharge_fail_closed(self):
        book=Quota(tenant_ceiling=10,global_ceiling=10)
        book.reserve("t","r",prompt=5,output=5)
        with self.assertRaises(Rejected):book.commit("t","r",prompt=6,output=2)
        self.assertEqual(book.commit("t","r",prompt=4,output=4)["charged_tokens"],8)
        with self.assertRaises(Rejected):book.commit("t","r",prompt=1,output=0)

if __name__=="__main__":
    unittest.main()
