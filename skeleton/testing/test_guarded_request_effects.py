"""Live domain acceptance for effects; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
import sqlite3
from skeleton.ai.runtime.operational_ai.guarded_request.receipts import EffectReceipts
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestEffectsGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'effects']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'effects']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_ambiguous_external_effect_stays_prepared(self):
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            ledger = EffectReceipts(db)
            ledger.prepare(scope="tenant", effect_id="e1", args_sha="a"*64)
            self.assertEqual(len(ledger.pending("tenant")), 1)
            self.assertEqual(ledger.prepare(
                scope="tenant", effect_id="e1", args_sha="a"*64), "prepared")
            ledger.close(scope="tenant", effect_id="e1", args_sha="a"*64,
                         committed=False, verified_receipt={"verified":True})
            self.assertEqual(ledger.pending("tenant"), [])
    def test_terminal_conflict_denied(self):
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            ledger = EffectReceipts(db)
            ledger.prepare(scope="tenant", effect_id="e1", args_sha="a"*64)
            ledger.close(scope="tenant", effect_id="e1", args_sha="a"*64,
                         committed=True, verified_receipt={"sha":"a"*64})
            with self.assertRaises(GateDenied):
                ledger.close(scope="tenant", effect_id="e1", args_sha="a"*64,
                             committed=False, verified_receipt={"sha":"a"*64})


if __name__ == '__main__':
    unittest.main()
