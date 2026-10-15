"""Scientific causal-signal conservatism for controlled native A/B comparisons."""
from __future__ import annotations
import unittest

from skeleton.jeeves.game_comparison_counterfactual import (
    _analyze_counterfactual,verify_counterfactual_input_result,
    ComparativeExperimentError,
)
from skeleton.jeeves.game_comparison_schema import digest
from tests.test_game_comparison_counterfactual_integrity import made_up_report


def repeated(arm:str, *, split:int=3, n:int=5, unstable:bool=False):
    rows=[]
    for repeat in (1,2,3):
        receipts=[]
        for step in range(1,n+1):
            kind=("shared" if step<split else arm)
            frame=digest(["frame",kind,step,repeat if unstable and repeat==3 else 0])
            pcm=digest(["pcm",kind,step,repeat if unstable and repeat==3 else 0])
            receipts.append({
                "native_frame_sha256":frame,"native_pcm_sha256":pcm,
                "observations":{"screen_mean":.3 if kind=="shared" else .4,
                                "visual_change":.2,"audio_rms":.1},
            })
        rows.append({"receipts":receipts})
    return rows


class ScientificCounterfactualContracts(unittest.TestCase):
    def test_matched_prefix_repeated_differences_are_only_candidates(self):
        a,b=repeated("baseline"),repeated("variant")
        report=_analyze_counterfactual(a,b,perturbation_step=3)
        self.assertTrue(report["pre_intervention_controls_matched"])
        self.assertEqual(report["scientific_evidence_status"],
                         "controlled_observable_signal_response_candidate")
        self.assertEqual(report["signal_comparison"]["video"][
            "first_repeatable_post_intervention_difference"],3)
        self.assertFalse(report["design_controls"]["causal_game_mechanic_proven"])
        self.assertEqual(report["production_model_weights_updated"],0)

    def test_preintervention_mismatch_blocks_mechanic_claim(self):
        a,b=repeated("baseline"),repeated("variant",split=1)
        report=_analyze_counterfactual(a,b,perturbation_step=3)
        self.assertFalse(report["pre_intervention_controls_matched"])
        self.assertEqual(report["scientific_evidence_status"],
                         "invalid_pre_intervention_divergence")
        self.assertFalse(report["post_intervention_observable_response_candidate"])

    def test_differing_repetitions_gate_out_signal_claim(self):
        a,b=repeated("baseline"),repeated("variant",unstable=True)
        report=_analyze_counterfactual(a,b,perturbation_step=3)
        self.assertFalse(report["repeat_consistent_in_both_arms"])
        self.assertEqual(report["scientific_evidence_status"],
                         "insufficient_native_repeatability")
        self.assertFalse(report["post_intervention_observable_response_candidate"])

    def test_unchanged_audio_video_do_not_invent_learning(self):
        a,b=repeated("shared"),repeated("shared")
        report=_analyze_counterfactual(a,b,perturbation_step=3)
        self.assertEqual(report["scientific_evidence_status"],
                         "no_repeatable_audiovisual_difference")
        self.assertFalse(report["post_intervention_observable_response_candidate"])

    def test_tampered_analysis_rejected_even_when_document_sha_recomputed(self):
        report=made_up_report()
        report["games"][0]["measured_analysis"]["pre_intervention_controls_matched"]=True
        report["result_sha256"]=digest({
            k:v for k,v in report.items() if k!="result_sha256"
        })
        with self.assertRaises(ComparativeExperimentError):
            verify_counterfactual_input_result(report)


if __name__=="__main__":
    unittest.main()
