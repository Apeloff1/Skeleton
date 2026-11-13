"""Source-backed typed request and adversarial denials for outbox_ack."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.runner import run_domain

class OutboxAckQualification(unittest.TestCase):
    def test_all_fourteen_real_python_source_cases(self):
        record=run_domain("outbox_ack")
        self.assertEqual(record["cases"],14)
        self.assertEqual((record["accepted"],record["rejected"],record["redacted"]),
                         (1,13,0))
    def test_fixture_accounting_is_deterministic(self):
        self.assertEqual(run_domain("outbox_ack"),run_domain("outbox_ack"))

if __name__=="__main__":
    unittest.main()
