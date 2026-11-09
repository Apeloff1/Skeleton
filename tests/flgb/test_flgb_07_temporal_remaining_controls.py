"""Remaining governed temporal controls: bounded cardinality and timeline isolation."""
from __future__ import annotations
from dataclasses import replace
from itertools import repeat
from types import SimpleNamespace
import unittest

from skeleton.ai.training.temporal_signals import TemporalSignalError
from skeleton.ai.training.temporal_budget import TemporalBudget, enforce_signal_budget, enforce_fact_budget
from skeleton.ai.training.temporal_counterfactual import CounterfactualBranch, CounterfactualOutcome, validate_counterfactual_outcome, require_observed_evidence_not_counterfactual
from skeleton.ai.training.temporal_intervals import YearInterval, require_temporal_compatibility
from skeleton.ai.training.temporal_editing import TemporalEdit, RippleConstraint, validate_temporal_edit

A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)


class TestRemainingTemporalControls(unittest.TestCase):
    def test_temporal_budget_bounds_unbounded_signal_generator(self):
        sample = SimpleNamespace(event_year=2025, source_digest=A)
        with self.assertRaisesRegex(TemporalSignalError, "signal budget exceeded"):
            enforce_signal_budget(repeat(sample), TemporalBudget(max_signals=3))
        self.assertEqual(enforce_signal_budget(iter([sample, sample]), TemporalBudget(max_signals=3)), (sample, sample))

    def test_temporal_fact_cardinality_is_bounded(self):
        sample = SimpleNamespace(source_digest=A)
        with self.assertRaisesRegex(TemporalSignalError, "fact budget exceeded"):
            enforce_fact_budget(repeat(sample), TemporalBudget(max_facts=2))
        with self.assertRaisesRegex(TemporalSignalError, "invalid temporal fact source"):
            enforce_fact_budget([SimpleNamespace(source_digest="bad")])

    def test_signal_year_span_and_source_identity_rejected(self):
        older = SimpleNamespace(event_year=2000, source_digest=A)
        newer = SimpleNamespace(event_year=2050, source_digest=B)
        with self.assertRaisesRegex(TemporalSignalError, "year span exceeded"):
            enforce_signal_budget([older, newer], TemporalBudget(max_year_span=25))
        with self.assertRaisesRegex(TemporalSignalError, "invalid temporal signal"):
            enforce_signal_budget([SimpleNamespace(event_year=True, source_digest=A)])

    def test_counterfactual_never_authorizes_observed_history(self):
        branch = CounterfactualBranch("what-if", A, B, 2025)
        outcome = CounterfactualOutcome(branch.digest, C, 2026, 900_000)
        self.assertEqual(validate_counterfactual_outcome(branch, outcome), outcome.digest)
        with self.assertRaisesRegex(TemporalSignalError, "counterfactual evidence"):
            require_observed_evidence_not_counterfactual(evidence_branch_digest=branch.digest)
        with self.assertRaisesRegex(TemporalSignalError, "counterfactual branch mismatch"):
            validate_counterfactual_outcome(branch, replace(outcome, branch_digest=D))
        with self.assertRaisesRegex(TemporalSignalError, "probability"):
            replace(outcome, probability_ppm=True)
        with self.assertRaisesRegex(TemporalSignalError, "fork year"):
            replace(branch, fork_year=True)

    def test_interval_relations_are_deterministic_and_type_safe(self):
        self.assertEqual(YearInterval(2020, 2025).relation(YearInterval(2025, 2030)), "meets")
        self.assertEqual(YearInterval(2025, 2030).relation(YearInterval(2020, 2025)), "met-by")
        self.assertEqual(YearInterval(2020, 2030).relation(YearInterval(2021, 2025)), "contains")
        self.assertEqual(YearInterval(2020, 2025).intersection(YearInterval(2025, 2030)), YearInterval(2025, 2025))
        with self.assertRaisesRegex(TemporalSignalError, "invalid interval year"):
            YearInterval(True, 2025)
        with self.assertRaisesRegex(TemporalSignalError, "temporally incompatible"):
            require_temporal_compatibility(YearInterval(2020, 2021), YearInterval(2030, 2035))

    def test_edit_requires_every_required_ripple_and_consistent_history(self):
        edit = TemporalEdit("edit-1", "subject", "is", A, B, 2026, "correction", C)
        ripple = RippleConstraint("ripple-1", edit.digest, D, "same-relation")
        with self.assertRaisesRegex(TemporalSignalError, "required edit ripple incomplete"):
            validate_temporal_edit(edit, historical_fact_digest=A, current_fact_digest=B, ripple_constraints=(ripple,))
        receipt = validate_temporal_edit(
            edit, historical_fact_digest=A, current_fact_digest=B,
            ripple_constraints=(ripple,), satisfied_ripple_digests=(ripple.digest,),
        )
        self.assertTrue(receipt.history_preserved)
        self.assertTrue(receipt.ripple_complete)
        with self.assertRaisesRegex(TemporalSignalError, "duplicate edit ripple constraint"):
            validate_temporal_edit(
                edit, historical_fact_digest=A, current_fact_digest=B,
                ripple_constraints=(ripple, ripple), satisfied_ripple_digests=(ripple.digest,),
            )
        with self.assertRaisesRegex(TemporalSignalError, "invalid temporal edit year"):
            replace(edit, effective_year=True)


if __name__ == "__main__":
    unittest.main()
