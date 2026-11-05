"""Cross-gate adversarial JSON and full source-backed coverage proof."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation,validate,domains
from skeleton.ai.runtime.operational_ai.trust_gates.contracts import canonical,load_json
from skeleton.ai.runtime.operational_ai.trust_gates.fixtures import run_all

class TrustGateCoreTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(GateViolation): load_json(b'{"x":1,"x":2}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(GateViolation): load_json(b'{"x":NaN}')
    def test_invalid_unicode_rejected(self):
        with self.assertRaises(GateViolation): canonical({"x":"\ud800"})
    def test_unknown_gate_rejected(self):
        with self.assertRaises(GateViolation): validate("system-execute",{})
    def test_exact_twenty_boundaries(self):
        self.assertEqual(len(domains()),20)
        self.assertEqual(len(set(domains())),20)
    def test_complete_real_predicate_fixture_execution(self):
        results=run_all()
        self.assertEqual(sum(v["total"] for v in results),240)
        self.assertEqual(sum(v["rejected"] for v in results),200)

if __name__=="__main__": unittest.main()
