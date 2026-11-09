"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
import concurrent.futures
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.quota import Quota
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class QuotaCases(unittest.TestCase):
    def test_two_parallel_reservations_cannot_double_spend(self):
        bank=Quota(tenant_ceiling=10,global_ceiling=20)
        def reserve(key):
            try: bank.reserve("tenant",key,prompt=7,output=3);return "admitted"
            except Rejected:return "held"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            self.assertCountEqual(list(ex.map(reserve,("a","b"))),("admitted","held"))
    def test_uncertain_effect_not_refunded(self):
        bank=Quota(tenant_ceiling=20,global_ceiling=20)
        bank.reserve("tenant","r",prompt=12,output=8)
        with self.assertRaises(Rejected):
            bank.release_without_effect("tenant","r",effect_absent=False)
        self.assertEqual(bank.commit("tenant","r",prompt=4,output=3)["charged_tokens"],7)
    def test_overcharge_does_not_clear_reservation(self):
        bank=Quota(tenant_ceiling=20,global_ceiling=20)
        bank.reserve("tenant","r",prompt=4,output=4)
        with self.assertRaises(Rejected):
            bank.commit("tenant","r",prompt=5,output=4)
        self.assertEqual(bank.snapshot()["pending_count"],1)
if __name__=="__main__":unittest.main()
