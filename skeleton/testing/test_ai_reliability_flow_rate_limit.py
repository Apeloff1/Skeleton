"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
import concurrent.futures
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.rate_window import RateWindow
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class RateBoundaries(unittest.TestCase):
    def test_parallel_credit_not_double_spent(self):
        gate=RateWindow(max_calls=1,period_ns=1000,clock=lambda:100)
        def try_gate(_):
            try:gate.admit("tenant");return True
            except Rejected:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            self.assertCountEqual(list(ex.map(try_gate,(0,1))),(True,False))
    def test_next_window_is_separate_epoch(self):
        now=[100]
        gate=RateWindow(max_calls=1,period_ns=100,clock=lambda:now[0])
        gate.admit("tenant")
        with self.assertRaises(Rejected):gate.admit("tenant")
        now[0]=201
        self.assertEqual(gate.admit("tenant")["admitted"],1)
if __name__=="__main__":unittest.main()
