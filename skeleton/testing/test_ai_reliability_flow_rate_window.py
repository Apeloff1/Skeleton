"""Focused operational AI reliability test: rate_window. No synthetic native E2E claim."""
import concurrent.futures
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.rate_window import RateWindow
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class RateTests(unittest.TestCase):
    def test_parallel_request_admission_remains_bounded(self):
        clock=lambda:100
        limit=RateWindow(max_calls=1,period_ns=1000,clock=clock)
        def request():
            try:limit.admit("tenant");return "yes"
            except Rejected:return "no"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _:request(),range(2)))
        self.assertCountEqual(outcomes,["yes","no"])
    def test_next_window_allows_new_request(self):
        now=[100]
        limit=RateWindow(max_calls=1,period_ns=100,clock=lambda:now[0])
        limit.admit("tenant")
        with self.assertRaises(Rejected):limit.admit("tenant")
        now[0]=201
        self.assertEqual(limit.admit("tenant")["admitted"],1)

if __name__=="__main__":
    unittest.main()
