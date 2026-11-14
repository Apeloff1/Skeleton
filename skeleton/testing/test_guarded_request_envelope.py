"""HMAC request-envelope unit and mutation checks; no hosted provider."""
from __future__ import annotations
from dataclasses import replace
import hashlib
import hmac
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.contracts import canonical_bytes
from skeleton.ai.runtime.operational_ai.guarded_request.identities import Scope
from skeleton.ai.runtime.operational_ai.guarded_request.signed_envelope import SignedEnvelope
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

MODEL = "a" * 64
PAYLOAD = "b" * 64
KEY = b"approved-local-secret" * 2


class TestEnvelope(unittest.TestCase):
    def setUp(self):
        self.scope = Scope("tenant", "user", "session", MODEL)
        self.envelope = SignedEnvelope.sign(
            KEY, scope=self.scope, nonce="request_1", sequence=1,
            payload_sha256=PAYLOAD, issued_ms=100, expires_ms=200,
        )

    def test_valid_envelope(self):
        self.envelope.verify(KEY, scope=self.scope, payload_sha256=PAYLOAD, now_ms=100)
        self.envelope.verify(KEY, scope=self.scope, payload_sha256=PAYLOAD, now_ms=199)

    def test_expiration_fails_closed(self):
        with self.assertRaises(GateDenied):
            self.envelope.verify(KEY, scope=self.scope, payload_sha256=PAYLOAD, now_ms=200)

    def test_wrong_principal(self):
        outsider = Scope("other", "user", "session", MODEL)
        with self.assertRaises(GateDenied):
            self.envelope.verify(KEY, scope=outsider, payload_sha256=PAYLOAD, now_ms=150)

    def test_wrong_key_and_payload(self):
        with self.assertRaises(GateDenied):
            self.envelope.verify(b"bad-key-material" * 3, scope=self.scope,
                                 payload_sha256=PAYLOAD, now_ms=150)
        with self.assertRaises(GateDenied):
            self.envelope.verify(KEY, scope=self.scope, payload_sha256="c" * 64, now_ms=150)

    def test_mutated_hmac(self):
        altered = replace(self.envelope, mac_sha256="0" * 64)
        with self.assertRaises(GateDenied):
            altered.verify(KEY, scope=self.scope, payload_sha256=PAYLOAD, now_ms=150)

    def test_expiration_window_bounded(self):
        with self.assertRaises(GateDenied):
            SignedEnvelope.sign(KEY, scope=self.scope, nonce="request_2",
                                sequence=2, payload_sha256=PAYLOAD,
                                issued_ms=1, expires_ms=300002)

    def test_authenticated_but_invalid_envelope_is_rejected(self):
        for fields in ({"expires_ms": 300101}, {"sequence": 0}, {"nonce": "bad nonce"},
                       {"issued_ms": -1}, {"expires_ms": True}):
            with self.subTest(fields=fields):
                invalid = replace(self.envelope, **fields)
                mac = hmac.new(KEY, canonical_bytes(invalid._payload()), hashlib.sha256).hexdigest()
                invalid = replace(invalid, mac_sha256=mac)
                with self.assertRaises(GateDenied):
                    invalid.verify(KEY, scope=self.scope, payload_sha256=PAYLOAD, now_ms=150)

    def test_malformed_wire_fields_fail_closed(self):
        for fields in ({"payload_sha256": 7}, {"sequence": True}, {"issued_ms": "100"}):
            with self.subTest(fields=fields):
                invalid = replace(self.envelope, **fields)
                with self.assertRaises(GateDenied):
                    invalid.verify(KEY, scope=self.scope, payload_sha256=PAYLOAD, now_ms=150)

    def test_manifest_schema_bound(self):
        self.assertEqual(self.envelope._payload()["schema"], "skeleton.ai.native-envelope.v1")


if __name__ == "__main__":
    unittest.main()
