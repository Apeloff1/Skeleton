"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class ValidationCases(QueueCase):
    def test_schema_rejects_nonfinite_temperature(self):
        import math
        for value in (float("nan"),float("inf"),-1,3,"0.8",True):
            with self.subTest(value=value):
                with self.assertRaises(Exception):
                    self.other_order(sampler_temperature=value)
    def test_identifiers_are_scope_bound(self):
        with self.assertRaises(WorkOrderError):self.other_order(job_id="../bad")
    def test_oversized_prompt_rejected(self):
        with self.assertRaises(WorkOrderError):
            self.other_order(prompt_text="X"*32769)
    def test_unicode_digest_uses_exact_utf8_bytes(self):
        text="snow ☃"
        special=self.other_order(job_id="unicode",request_id="unicode",prompt_text=text)
        self.assertEqual(special.confirm_prompt(text),text)
        with self.assertRaises(WorkOrderError):special.confirm_prompt("snow ❄")

if __name__=="__main__":unittest.main()
