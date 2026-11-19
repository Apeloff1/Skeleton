"""Live domain acceptance for nonce; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
import sqlite3
from skeleton.ai.runtime.operational_ai.guarded_request.nonce_fence import NonceFence
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestNonceGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'nonce']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'nonce']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_monotonic_and_true_replay(self):
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            fence = NonceFence(db)
            self.assertEqual(fence.reserve("tenant", "n1", 1, "a"*64), "admitted")
            self.assertEqual(fence.reserve("tenant", "n1", 1, "a"*64), "replayed")
            with self.assertRaises(GateDenied):
                fence.reserve("tenant", "n1", 1, "b"*64)
            with self.assertRaises(GateDenied):
                fence.reserve("tenant", "n2", 1, "a"*64)
            self.assertEqual(fence.head("tenant"), 1)
    def test_sequence_requires_real_integer(self):
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            with self.assertRaises(GateDenied):
                NonceFence(db).reserve("tenant", "n1", True, "a"*64)



class TestOversizedNegativeFixture(unittest.TestCase):
    def test_fixture_boundary_and_runtime_denial(self):
        from skeleton.ai.runtime.operational_ai.guarded_request.contracts import (
            MAX_TEXT_CHARS, parse_json,
        )
        from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import _read_fixture
        import json

        cases = {case["id"]: case for case in iter_scenarios()
                 if case["id"] in ("tokens-10", "tokens-24")}
        self.assertEqual(set(cases), {"tokens-10", "tokens-24"})
        self.assertEqual(len(cases["tokens-10"]["input"]["prompt"]), MAX_TEXT_CHARS)
        self.assertEqual(len(cases["tokens-24"]["input"]["prompt"]), MAX_TEXT_CHARS + 1)
        self.assertTrue(evaluate("tokens", cases["tokens-10"]["input"])["allowed"])
        self.assertEqual(evaluate("tokens", cases["tokens-24"]["input"]),
                         {"allowed": False, "code": "prompt-text"})

        # Application ingress must still reject the over-limit fixture.
        raw = json.dumps(cases["tokens-24"]).encode("utf-8")
        with self.assertRaises(GateDenied) as denied:
            parse_json(raw)
        self.assertEqual(denied.exception.code, "json-text")

        # An altered allow claim, changed sentinel or unknown file cannot
        # exploit the one named negative-vector exception.
        for changed in (
            {**cases["tokens-24"], "expected_allow": True},
            {**cases["tokens-24"], "input": {
                **cases["tokens-24"]["input"], "prompt": "y" * (MAX_TEXT_CHARS + 1),
            }},
        ):
            with self.assertRaises(AssertionError):
                _read_fixture(json.dumps(changed).encode("utf-8"),
                              domain="tokens", filename="tokens-24.json")
        with self.assertRaises(GateDenied):
            _read_fixture(raw, domain="nonce", filename="tokens-24.json")
        with self.assertRaises(GateDenied):
            _read_fixture(raw, domain="tokens", filename="tokens-25.json")


if __name__ == '__main__':
    unittest.main()
