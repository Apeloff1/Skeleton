"""Focused canonical/denial-code regressions for exact-source AI contracts."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.guarded_request.budgets import Quota
from skeleton.ai.runtime.operational_ai.guarded_request.contracts import (
    canonical_bytes, digest, parse_json, strict_integer,
)
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied, deny


class TestGuardedContractDenials(unittest.TestCase):
    def test_underscore_bearing_quota_code_is_a_policy_denial(self):
        with self.assertRaises(GateDenied) as error:
            strict_integer(True, minimum=1, maximum=10, field="context_tokens")
        self.assertEqual(error.exception.code, "context_tokens-range")

    def test_rejects_unbounded_or_unsafe_code_names(self):
        for bad in ("", "UPPERCASE", "a/b", "a\nb", "a"*129, 7):
            with self.subTest(code=repr(bad)), self.assertRaises(ValueError):
                GateDenied(bad)

    def test_duplicate_json_keys_fail_before_schema(self):
        with self.assertRaises(GateDenied) as error:
            parse_json(b'{"principal":"alice","principal":"mallory"}')
        self.assertEqual(error.exception.code, "json-duplicate")

    def test_nonfinite_json_denied(self):
        with self.assertRaises(GateDenied):
            parse_json(b'{"x":NaN}')
        with self.assertRaises(GateDenied):
            canonical_bytes({"x": float("inf")})

    def test_hash_order_invariance(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))

    def test_boolean_not_integer_quota(self):
        with self.assertRaises(GateDenied) as error:
            Quota(context_tokens=True)
        self.assertEqual(error.exception.code, "context_tokens-range")

    def test_untrusted_json_depth_is_finite(self):
        with self.assertRaises(GateDenied):
            canonical_bytes([[[[[[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]]]]]])

    def test_valid_code_still_survives(self):
        with self.assertRaises(GateDenied) as error:
            deny("model_token-budget-exhausted")
        self.assertEqual(error.exception.code, "model_token-budget-exhausted")


if __name__ == "__main__":
    unittest.main()
