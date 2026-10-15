"""Offline native A/B experiment viewer contracts, synthetic evidence only."""
from __future__ import annotations

import unittest
from tests.test_game_comparison_counterfactual_integrity import made_up_report
from skeleton.jeeves.game_comparison_counterfactual_viewer import render_counterfactual_game_dashboard
from skeleton.jeeves.game_comparison_counterfactual import ComparativeExperimentError


class ComparativeExperimentOfflineViewerTests(unittest.TestCase):
    def test_verified_study_has_graphs_and_receipts(self):
        page=render_counterfactual_game_dashboard(made_up_report())
        self.assertIn("Controlled native game experiments",page)
        self.assertIn('id="visual"',page)
        self.assertIn('id="audio"',page)
        self.assertIn("Step chain",page)
        self.assertNotIn("<script src=",page)
        self.assertNotIn("https://",page)
        self.assertIn("real",page.lower())
        self.assertIn("no game content embedded",page)

    def test_altered_native_step_cannot_be_visualized_as_proof(self):
        report=made_up_report()
        report["games"][1]["perturbed_fresh_native_runs"][0]["receipts"][1]["native_pcm_sha256"]="0"*64
        with self.assertRaises(ComparativeExperimentError):
            render_counterfactual_game_dashboard(report)


if __name__=="__main__":
    unittest.main()
