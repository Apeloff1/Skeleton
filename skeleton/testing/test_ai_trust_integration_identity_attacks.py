"""Malformed serialized identities and Unicode ambiguity are refused."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.contracts import canonical,load_json
from skeleton.ai.runtime.operational_ai.trust_gates.fixtures import run_domain

class CanonicalAttackCases(unittest.TestCase):
    def test_duplicate_properties_refused(self):
        for raw in (b'{"x":1,"x":1}', b'{"x":1,"x":2}',
                    b'{"outer":{"x":1,"x":2}}'):
            with self.subTest(raw=raw):
                with self.assertRaises(GateViolation):load_json(raw)
    def test_nonfinite_numbers_refused(self):
        for raw in (b'{"x":NaN}',b'{"x":Infinity}',b'{"x":-Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(GateViolation):load_json(raw)
    def test_explicit_bounded_unicode(self):
        with self.assertRaises(GateViolation):canonical({"x":"\udfff"})
        self.assertEqual(load_json(canonical({"x":"snow ☃"})),{"x":"snow ☃"})
    def test_no_unknown_actor_privilege(self):
        self.assertEqual(run_domain("actor")["rejected"],10)
    def test_no_unauthorized_tool_path(self):
        self.assertEqual(run_domain("tool")["rejected"],10)
    def test_payload_overflow_rejected(self):
        with self.assertRaises(GateViolation):load_json(b'{' + b' '*524288 + b'}')

if __name__=="__main__": unittest.main()
