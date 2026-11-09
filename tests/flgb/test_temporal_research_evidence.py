"""End-to-end temporal retrieval, drift and research authority contracts."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from skeleton.ai.training.temporal_signals import TemporalSignalError
from skeleton.ai.training.temporal_facts import TemporalFact, snapshot_facts
from skeleton.ai.training.temporal_retrieval import (
    TemporalQuery, retrieve_temporal_facts, qualify_temporal_retrieval,
)
from skeleton.ai.training.temporal_drift import (
    ForecastObservation, score_calibration, adaptive_drift_window,
    update_change_point_state,
)
from skeleton.ai.training.temporal_research_authority import (
    authorize_research_temporal_plane,
)


class TestHistoricalRetrieval(unittest.TestCase):
    def facts(self):
        first = TemporalFact("f1", "runtime", "is", "a" * 64, 2020, 2040, 2022, "1" * 64)
        later = TemporalFact("f2", "runtime", "is", "b" * 64, 2020, 2040, 2027, "2" * 64)
        return first, later

    def test_historical_snapshot_excludes_future_observations(self):
        first, future = self.facts()
        query = TemporalQuery("q", "runtime", 2025, "historical", "3" * 64)
        result = retrieve_temporal_facts((first, future), query)
        self.assertEqual(result.excluded_future_count, 1)
        self.assertEqual(result.result_fact_digests, (first.digest,))
        self.assertTrue(result.leakage_free)
        self.assertEqual(result.digest, retrieve_temporal_facts((first, future), query).digest)

    def test_temporal_evidence_needs_independent_sources(self):
        first, future = self.facts()
        result = retrieve_temporal_facts((first, future), TemporalQuery("q", "runtime", 2029, "current", "3" * 64))
        qualification = qualify_temporal_retrieval(result, (first, future), temporal_authority_digest="4" * 64)
        self.assertTrue(qualification.qualified)
        self.assertEqual(qualification.source_count, 2)
        with self.assertRaisesRegex(TemporalSignalError, "insufficient independent"):
            qualify_temporal_retrieval(result, (first, future), temporal_authority_digest="4" * 64, min_sources=3)

    def test_extrapolation_is_never_retrieval_evidence(self):
        with self.assertRaises(TemporalSignalError):
            retrieve_temporal_facts(self.facts(), TemporalQuery("q", "runtime", 2030, "extrapolation", "3" * 64))

    def test_booleans_and_missing_years_fail_closed(self):
        for invalid in (True, False, 0, 2201):
            with self.assertRaises(TemporalSignalError):
                TemporalQuery("q", "runtime", invalid, "historical", "3" * 64)
        with self.assertRaises(TemporalSignalError):
            TemporalQuery("q", "runtime", 2025, "current", "3" * 64, max_results=True)
        with self.assertRaises(TemporalSignalError):
            snapshot_facts(self.facts(), as_of_year=True)
        with self.assertRaises(TemporalSignalError):
            TemporalFact("x", "runtime", "is", "a" * 64, True, 2040, 2022, "1" * 64)


class TestCalibrationAndAuthority(unittest.TestCase):
    def calibration(self):
        return score_calibration((
            ForecastObservation("yes", 2024, 1_000_000, True, "1" * 64),
            ForecastObservation("no", 2024, 0, False, "2" * 64),
        ))

    def window(self):
        return adaptive_drift_window(
            ((2020, 900_000), (2021, 800_000), (2022, 100_000), (2023, 200_000)),
            subject="runtime", min_window=2, threshold_ppm=200_000,
        )

    def test_perfect_calibration_and_drift_detection(self):
        score = self.calibration()
        self.assertEqual(score.brier_ppm, 0)
        self.assertEqual(score.calibration_error_ppm, 0)
        self.assertTrue(self.window().drift)
        with self.assertRaisesRegex(TemporalSignalError, "duplicate drift year"):
            adaptive_drift_window(((2020, 100), (2020, 200), (2021, 300), (2022, 400)), subject="runtime")

    def test_research_gate_requires_calibration_and_distinct_bases(self):
        snap = snapshot_facts((), as_of_year=2026)
        state = update_change_point_state(self.window(), policy_year=2026, hazard_ppm=100_000)
        temporal = SimpleNamespace(subject="runtime", policy_year=2026, digest="f" * 64)
        arguments = dict(
            subject="runtime", policy_year=2026, temporal_receipt=temporal,
            calibration_receipt=self.calibration(), change_point_state=state,
            historical_snapshot=snap,
            research_basis_digests=("a" * 64, "b" * 64, "c" * 64),
        )
        accepted = authorize_research_temporal_plane(**arguments)
        self.assertTrue(accepted.authorized)
        self.assertEqual(accepted.digest, authorize_research_temporal_plane(**arguments).digest)
        with self.assertRaisesRegex(TemporalSignalError, "duplicate research basis"):
            authorize_research_temporal_plane(**{**arguments, "research_basis_digests": ("a" * 64,) * 3})
        with self.assertRaisesRegex(TemporalSignalError, "regime change"):
            authorize_research_temporal_plane(**{**arguments, "change_point_state": replace(state, change_probability_ppm=700_000)})
        with self.assertRaisesRegex(TemporalSignalError, "time mismatch"):
            authorize_research_temporal_plane(**{**arguments, "policy_year": 2025})
        bad_score = replace(self.calibration(), brier_ppm=400_000)
        with self.assertRaisesRegex(TemporalSignalError, "Brier score"):
            authorize_research_temporal_plane(**{**arguments, "calibration_receipt": bad_score})

    def test_malformed_calibration_observations_are_rejected(self):
        with self.assertRaises(TemporalSignalError):
            ForecastObservation("a", 2026, True, True, "1" * 64)
        with self.assertRaises(TemporalSignalError):
            ForecastObservation("a", 2026, 500_000, True, "bad")
        with self.assertRaises(TemporalSignalError):
            ForecastObservation("a", False, 500_000, True, "1" * 64)


if __name__ == "__main__":
    unittest.main()
