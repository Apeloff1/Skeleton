"""Lower-trust credential envelope redaction, with explicit non-completeness."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.redaction import (
    redact_credential_envelopes,
)


class TestCredentialEnvelopeRedaction(unittest.TestCase):
    def test_bearer_value_is_not_exposed(self):
        output, count = redact_credential_envelopes("Bearer "+"A"*48+" evidence")
        self.assertNotIn("A"*48, output)
        self.assertEqual(count, 1)

    def test_api_key_assignment(self):
        output, count = redact_credential_envelopes("api_key="+("q"*24))
        self.assertNotIn("q"*24, output)
        self.assertEqual(count, 1)

    def test_no_evidence_modification_without_pattern(self):
        text = "Physics notes about conservation of energy."
        self.assertEqual(redact_credential_envelopes(text), (text, 0))


if __name__ == "__main__":
    unittest.main()
