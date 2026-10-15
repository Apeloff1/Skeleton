"""Synthetic receipt-chain tamper checks; does not run or observe real game content."""
from __future__ import annotations
import unittest
from skeleton.jeeves.game_comparison_schema import digest
from skeleton.jeeves.game_comparison_counterfactual import (
    verify_counterfactual_input_result,ComparativeExperimentError,
    _analyze_counterfactual,
)
from skeleton.ai.webcrawler.dragon_comparative_game_bridge import export_dragon_counterfactual_review


def made_up_report():
    registry=digest(["synthetic-registry"])
    report={
        "schema_version":"skeleton.game.comparison_counterfactual_input_v1",
        "source_study_id":"fixture_not_a_game",
        "source_manifest_sha256":digest(["study"]),
        "operator_core_registry_sha256":registry,
        "input_step":2,"replacement_action":"left","games":[],
        "actual_native_content_required":True,
        "source_game_logic_reverse_engineered":False,
        "holdout_validation_completed":False,
        "dragon_review_authority_granted":False,
        "production_model_weights_promoted":False,
    }
    for game_id in ("fake_one","fake_two"):
        source=digest(["source",game_id])
        repetitions={}
        for arm in ("baseline","perturbed"):
            actions=["idle","right" if arm=="baseline" else "left","a"]
            runs=[]
            for repetition in (1,2):
                previous=digest([
                    "comparative-controlled-native-run",
                    registry,source,game_id,arm,repetition,123,
                ])
                entries=[]
                for i,action in enumerate(actions,1):
                    entry={
                        "step":i,"action":action,"source":"actual_isolated_libretro",
                        "source_game_sha256":source,
                        "core_sha256":digest(["fixture-core",game_id]),
                        "native_frame_sha256":digest(["pixels",game_id,arm,i]),
                        "native_pcm_sha256":digest(["pcm",game_id,arm,i]),
                        "native_transition_sha256":digest(["transition",game_id,arm,i]),
                        "observations":{
                            "screen_mean":0.2,"visual_change":0.4,
                            "audio_rms":0.3,"step_fraction":i/3,
                        },
                        "native_gameplay_goal_verified":False,
                    }
                    previous=digest([previous,entry])
                    entry["receipt_chain_sha256"]=previous
                    entries.append(entry)
                runs.append({
                    "arm":arm,"repeat":repetition,
                    "actions_sha256":digest(actions),"seed":123,
                    "native_steps_executed":len(entries),"receipts":entries,
                    "last_evidence_sha256":previous,
                    "real_native_run":True,"fresh_worker_requested":True,
                    "external_execution_attestation":False,
                })
            repetitions[arm]=runs
        report["games"].append({
            "game_id":game_id,"core_id":"fceumm","target_id":"nes",
            "source_sha256":source,"perturbation_step":2,
            "baseline_action":"right","alternative_action":"left",
            "original_actions_sha256":digest(["idle","right","a"]),
            "perturbed_actions_sha256":digest(["idle","left","a"]),
            "baseline_fresh_native_runs":repetitions["baseline"],
            "perturbed_fresh_native_runs":repetitions["perturbed"],
            "measured_analysis":_analyze_counterfactual(
                repetitions["baseline"],repetitions["perturbed"],
                perturbation_step=2,
            ),
            "source_rights_independently_verified":False,
        })
    report["game_count"]=2
    report["fresh_native_runs_attempted"]=8
    report["fresh_native_runs_completed"]=8
    report["result_sha256"]=digest(report)
    return report


class FakeCounterfactualChainContracts(unittest.TestCase):
    def test_full_chain_and_dragon_knowledge_remain_review_only(self):
        fake=made_up_report()
        verified=verify_counterfactual_input_result(fake)
        self.assertEqual(verified["fresh_native_runs_hash_checked"],8)
        self.assertEqual(verified["native_action_observations_hash_checked"],24)
        proposal=export_dragon_counterfactual_review(fake)
        self.assertEqual(proposal["native_evidence_verification_sha256"],
                         verified["verification_sha256"])
        self.assertFalse(proposal["weights_or_longterm_memory_changed"])

    def test_altered_step_fails_even_if_document_root_is_rehashed(self):
        fake=made_up_report()
        fake["games"][0]["baseline_fresh_native_runs"][0]["receipts"][1]["action"]="a"
        fake["result_sha256"]=digest({
            k:v for k,v in fake.items() if k!="result_sha256"
        })
        with self.assertRaises(ComparativeExperimentError):
            verify_counterfactual_input_result(fake)
        with self.assertRaises(ComparativeExperimentError):
            export_dragon_counterfactual_review(fake)


if __name__=="__main__":
    unittest.main()
