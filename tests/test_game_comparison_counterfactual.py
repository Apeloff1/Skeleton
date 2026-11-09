"""Counterfactual AI game lab contracts using synthetic metadata only.

No emulator executable, ROM, user files, screenshots or learned model
weights are accessed in these unit-contract tests.
"""
from __future__ import annotations

import unittest

from skeleton.jeeves.game_comparison_counterfactual import (
    _analyze_counterfactual,_validate_design,ComparativeExperimentError,
)
from skeleton.jeeves.game_comparison_schema import digest


def study():
    games=[]
    for i,name in enumerate(("test_one","test_two"),1):
        games.append({
            "id":name,"title":name,
            "series_id":"synthetic_series",
            "release_order":i,"release_year":2026,
            "series_phase":"earlier" if i==1 else "middle",
            "target_id":"nes","core_id":"fceumm",
            "source_path":"/synthetic/"+name+".nes",
            "source_sha256":digest(["fictional-test-bytes",name]),
            "rights_evidence_digest":digest(["fixture-rights",name]),
            "actions":["idle","right","a"],
            "seed":123,"frames_per_step":1,
            "controller_devices":["joypad"],
        })
    return {
        "schema_version":"skeleton.game.comparative_study.v1",
        "study_id":"synthetic_counterfactual",
        "title":"Fixture only - no game",
        "games":games,
        "pairs":[{"left_id":"test_one","right_id":"test_two","questions":[]}],
        "notes":[],"max_active":2,
    }


def arm(kind,number):
    return {"receipts":[
        {"native_frame_sha256":digest([kind,"video",i]),
         "native_pcm_sha256":digest([kind,"pcm",i]),
         "observations":{"screen_mean":.1 if kind=="baseline" else .3,
                         "visual_change":.2,"audio_rms":.4}}
        for i in range(3)
    ],"repeat":number}


class CounterfactualInputContracts(unittest.TestCase):
    def test_one_action_difference_in_all_games(self):
        model,rows=_validate_design(
            study(),game_ids=["test_one","test_two"],step=2,
            replacement_action="left",repeats=3,
        )
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["actions"][1],"right")

    def test_identical_input_rejected(self):
        with self.assertRaises(ComparativeExperimentError):
            _validate_design(study(),game_ids=["test_one","test_two"],step=2,
                             replacement_action="right",repeats=2)

    def test_missing_game_rights_record_rejected(self):
        s=study()
        s["games"][0]["rights_evidence_digest"]=None
        with self.assertRaises(ComparativeExperimentError):
            _validate_design(s,game_ids=["test_one","test_two"],step=2,
                             replacement_action="left",repeats=2)

    def test_repeated_observation_difference_does_not_claim_ai_learning(self):
        result=_analyze_counterfactual(
            [arm("baseline",1),arm("baseline",2)],
            [arm("changed",1),arm("changed",2)],
            perturbation_step=2,
        )
        self.assertTrue(result["repeat_consistent_in_both_arms"])
        self.assertTrue(result["signal_comparison"]["video"][
            "difference_at_perturbed_input_step"])
        self.assertFalse(result["design_controls"]["causal_game_mechanic_proven"])
        self.assertFalse(result["heldout_learning_gain_verified"])
        self.assertEqual(result["production_model_weights_updated"],0)


if __name__=="__main__":
    unittest.main()
