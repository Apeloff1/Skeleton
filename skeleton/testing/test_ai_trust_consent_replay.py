"""HMAC memory consent replay, scope, expiry and malformed-input regression."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.control.consent import ConsentAuthority

class ConsentReplay(unittest.TestCase):
    def setUp(self):
        self.authority=ConsentAuthority(b"K"*32,maximum_consumed=2)
    def issue(self,now=10,expires=30):
        return self.authority.issue(tenant="local",source_id="note",
            operator="owner",now=now,expires=expires,approved=True)
    def test_single_use_nonce(self):
        token=self.issue()
        self.assertTrue(self.authority.verify(token,tenant="local",
                                               source_id="note",now=11)["approved"])
        with self.assertRaises(GateViolation):
            self.authority.verify(token,tenant="local",source_id="note",now=12)
    def test_two_independent_tokens_use_distinct_nonce(self):
        first=self.issue();second=self.issue()
        self.assertNotEqual(first["record"]["nonce"],second["record"]["nonce"])
        self.authority.verify(first,tenant="local",source_id="note",now=12)
        self.authority.verify(second,tenant="local",source_id="note",now=12)
        with self.assertRaises(GateViolation):
            self.authority.verify(self.issue(),tenant="local",source_id="note",now=12)
    def test_tampered_record_is_denied(self):
        token=self.issue()
        token["record"]["source_id"]="other"
        with self.assertRaises(GateViolation):
            self.authority.verify(token,tenant="local",source_id="other",now=12)
    def test_false_scope_never_consumes_legitimate_token(self):
        token=self.issue()
        with self.assertRaises(GateViolation):
            self.authority.verify(token,tenant="other",source_id="note",now=12)
        self.assertTrue(self.authority.verify(token,tenant="local",
                                              source_id="note",now=12)["approved"])
    def test_future_and_expired_consent_denied(self):
        token=self.issue()
        for now in (9,30):
            with self.subTest(now=now):
                with self.assertRaises(GateViolation):
                    self.authority.verify(token,tenant="local",source_id="note",now=now)
    def test_untrusted_clock_type_denied(self):
        token=self.issue()
        with self.assertRaises(GateViolation):
            self.authority.verify(token,tenant="local",source_id="note",now="11")
    def test_weak_key_and_invalid_principal_denied(self):
        with self.assertRaises(GateViolation):ConsentAuthority(b"short")
        with self.assertRaises(GateViolation):
            self.authority.issue(tenant="a\nb",source_id="note",
                operator="owner",now=10,expires=20,approved=True)

if __name__=="__main__":
    unittest.main()
