"""Run-state fences forbid restart of uncertain gradients and skipped checks."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.lifecycle import GenesisState
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestGenesisLifecycle(unittest.TestCase):
    def test_allowed_stages_in_order(self):
        state=GenesisState("original_run")
        for target in ("source_admitted","vocab_built","initialized",
                       "published_genesis","training","candidate_published",
                       "candidate_review","held"):
            state=state.advance(target)
        self.assertEqual(state.revision,8)
        self.assertEqual(state.stage,"held")
        self.assertFalse(state.report()["production_authorized"])

    def test_no_automatic_admission_shortcut(self):
        with self.assertRaises(GenesisRejected):
            GenesisState("original_run").advance("candidate_published")

    def test_training_failure_becomes_uncertain_hold(self):
        state=GenesisState("original_run","training").advance("uncertain")
        self.assertEqual(state.advance("held").stage,"held")
        with self.assertRaises(GenesisRejected):
            state.advance("candidate_published")

    def test_held_is_terminal(self):
        with self.assertRaises(GenesisRejected):
            GenesisState("original_run","held").advance("initialized")

    def test_skipped_source_checks_refused(self):
        with self.assertRaises(GenesisRejected):
            GenesisState("original_run","requested").advance("vocab_built")

    def test_no_production_state_exists(self):
        with self.assertRaises(GenesisRejected):
            GenesisState("original_run","production_serving")


if __name__=="__main__":
    unittest.main()
