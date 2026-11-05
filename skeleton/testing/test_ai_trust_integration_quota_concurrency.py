"""Concurrent reservation admission cannot double-spend process-local quota."""
import concurrent.futures
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.applications.quota_book import QuotaBook

class QuotaConcurrency(unittest.TestCase):
    def test_two_workers_do_not_overspend_same_tenant(self):
        book=QuotaBook(tenant_ceiling=10,global_ceiling=10)
        def reserve(r):
            try:
                book.reserve("tenant",r,prompt_tokens=7,output_tokens=0)
                return "admitted"
            except GateViolation: return "blocked"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,["r1","r2"]))
        self.assertEqual(sorted(results),["admitted","blocked"])
    def test_release_refunds_reserved_not_committed_tokens(self):
        book=QuotaBook(tenant_ceiling=20,global_ceiling=20)
        book.reserve("a","r1",prompt_tokens=12,output_tokens=8)
        with self.assertRaises(GateViolation):
            book.reserve("a","r2",prompt_tokens=1,output_tokens=1)
        book.release("a","r1")
        self.assertEqual(book.reserve("a","r2",prompt_tokens=1,
                                     output_tokens=1)["status"],"accepted")
    def test_committed_usage_remains_consumed(self):
        book=QuotaBook(tenant_ceiling=10,global_ceiling=10)
        book.reserve("a","r",prompt_tokens=7,output_tokens=3)
        self.assertEqual(book.commit("a","r",actual_prompt=7,
                                     actual_output=3)["charged_tokens"],10)
        with self.assertRaises(GateViolation):
            book.reserve("a","next",prompt_tokens=1,output_tokens=0)

if __name__=="__main__": unittest.main()
