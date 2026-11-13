"""Real Actor-to-policy admission adapter with no synthetic text generation."""
import unittest
from skeleton.ai.runtime.operational_ai.authority.identity import Actor
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.integration import preflight_turn

class NativePreflight(unittest.TestCase):
    def setUp(self):
        self.actor=Actor("local","operator","a"*64,"a"*64)
    def check(self, **overrides):
        args={"actor":self.actor,"request_id":"r1","seed":5,"temperature":1.0,
              "max_output_tokens":128,"context_window":2048,"queue_depth":0,
              "queue_ceiling":10,"now_ns":100,"deadline_ns":200}
        args.update(overrides)
        return preflight_turn(**args)
    def test_three_real_contract_receipts_before_generation(self):
        records=self.check()
        self.assertEqual([r["gate"] for r in records],["actor","sampling","admission"])
        self.assertTrue(all(r["status"]=="accepted" for r in records))
    def test_expired_model_operation_refused(self):
        with self.assertRaises(GateViolation):self.check(now_ns=201)
    def test_queue_saturation_refused(self):
        with self.assertRaises(GateViolation):self.check(queue_depth=10)
    def test_illegal_sampler_refused(self):
        with self.assertRaises(GateViolation):self.check(temperature=0.0)
    def test_model_resource_overcommit_refused(self):
        with self.assertRaises(GateViolation):self.check(max_output_tokens=2048)
    def test_duplicate_trust_receipts_are_deterministic(self):
        self.assertEqual(self.check(),self.check())

if __name__=="__main__": unittest.main()
