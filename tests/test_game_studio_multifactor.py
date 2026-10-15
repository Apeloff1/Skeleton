"""Real, bounded multi-item/ability/tool/weapon/control/environment joint training."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_multifactor import (
    CATEGORIES, MultiFactorError, multifactor_capabilities,
    plan_multifactor_scenarios, execute_multifactor_scenarios,
)


class MultifactorExperimentTests(unittest.TestCase):
    def setUp(self):
        self.source=make_studio_source(
            "economy",{"market_nodes":3,"goods":10},
            actions=("inspect","survey","wait","buy:1","sell:1","produce"),
        )

    def test_every_requested_factor_is_declared_even_when_engine_cannot_execute_it(self):
        cap=multifactor_capabilities(self.source)
        groups={x["category"]:x for x in cap["categories"]}
        for name in (
            "items","abilities","weapons","tools","style","movement",
            "expression","reaction","consequence","actions","environment",
            "ambience","music","apparel","status_effects","npc_behavior",
            "physics","camera","time","accessibility","network","save_load",
        ):
            self.assertIn(name,groups)
        self.assertEqual(groups["items"]["status"],"executable_logic")
        self.assertEqual(groups["economy"]["status"],"executable_logic")
        self.assertEqual(groups["expression"]["status"],"unimplemented_for_this_engine")
        self.assertFalse(cap["native_music_audio_expression_rendering_assumed"])
        self.assertGreater(cap["total_executable_axes"],1)
        self.assertTrue(all(a["kind"] in ("source_field","registered_action")
                            for a in cap["available_axes"]))
        self.assertTrue(all(not group["real_physical_modality_certified"]
                            for group in cap["categories"]))

    def test_high_order_design_is_coverage_bounded_and_source_validated(self):
        plan=plan_multifactor_scenarios(
            self.source,interaction_order=3,max_scenarios=8,
        )
        self.assertGreaterEqual(len(plan["scenarios"]),2)
        self.assertLessEqual(len(plan["scenarios"]),8)
        self.assertLessEqual(plan["bounded_candidate_worlds_considered"],513)
        self.assertFalse(plan["full_cross_product_enumerated"])
        self.assertEqual(plan["editor"],"economy")
        self.assertGreater(plan["covered_interactions"],0)
        for experiment in plan["scenarios"]:
            self.assertEqual(experiment["source"]["editor"],"economy")
            self.assertEqual(experiment["source"]["actions"],self.source["actions"])
            self.assertTrue(experiment["changed_axes"])
            self.assertEqual(len(experiment["source_digest"]),64)
        with self.assertRaises(MultiFactorError):
            plan_multifactor_scenarios(self.source,axis_offset=63)

    def test_real_ablations_executed_independently_from_source(self):
        prior=deepcopy(self.source)
        result=execute_multifactor_scenarios(
            self.source,max_scenarios=3,steps=2,seed=13,
            train=False,
        )
        self.assertEqual(self.source,prior)
        self.assertEqual(result["actual_q_weight_updates"],0)
        self.assertTrue(all(
            set(entry["selected_registered_actions"][:2]).issubset(
                set(result["experiments"][entry["index"]]["scripted_actions"])
            ) for entry in result["plan"]["scenarios"]
            if len(entry["selected_registered_actions"])<=2
        ))
        self.assertFalse(result["production_neural_weights_modified"])
        self.assertFalse(result["automatic_promotion"])
        self.assertGreaterEqual(result["scenarios_executed"],2)
        for row in result["experiments"]:
            self.assertTrue(row["variant_source_verified"])
            self.assertEqual(len(row["control_audit_digest"]),64)
            self.assertEqual(len(row["variant_audit_digest"]),64)
            self.assertIsNone(row["actual_weight_training"])
            self.assertFalse(row["native_audio_or_visual_content_created"])
            for removed in row["factor_ablation_receipts"]:
                self.assertTrue(removed["source_verified"])
                self.assertEqual(len(removed["audit_digest"]),64)
            if row["pairwise_interaction_witness"] is not None:
                self.assertFalse(row["pairwise_interaction_witness"][
                    "mechanical_causal_generalization_proven"])

    def test_actual_local_Q_parameter_and_holdout_receipts(self):
        with self.assertRaises(PermissionError):
            execute_multifactor_scenarios(
                self.source,max_scenarios=2,steps=2,train=True,
            )
        result=execute_multifactor_scenarios(
            self.source,max_scenarios=2,steps=2,seed=8,
            train=True,authorized=True,rights_cleared=True,
        )
        self.assertEqual(result["scenarios_executed"],2)
        self.assertGreater(result["actual_q_weight_updates"],0)
        self.assertGreater(result["newly_visited_q_parameters"],0)
        for row in result["experiments"]:
            training=row["actual_weight_training"]
            self.assertGreater(training["actual_training_updates"],0)
            self.assertEqual(len(training["training_trace_digests"]),3)
            self.assertEqual(len(training["heldout_seeds"]),2)
            self.assertTrue(set(training["heldout_seeds"]).isdisjoint(
                {row["seed"]+9000+i for i in range(3)}
            ))
            gain=training["parameter_gain"]
            efficiency=training["measured_learning_efficiency"]
            self.assertGreater(efficiency["actual_q_updates"],0)
            self.assertGreaterEqual(efficiency["accepted_game_actions"],0)
            self.assertEqual(efficiency["neural_parameter_updates_observed"],0)
            self.assertFalse(efficiency["claimed_converged_or_SOTA"])
            self.assertEqual(len(training["training_episode_actions"]),3)
            self.assertTrue(all(
                1<=len(e["actions"])<=2 and len(e["trace_digest"])==64
                for e in training["training_episode_actions"]
            ))
            self.assertGreater(gain["newly_visited_state_action_parameters"],0)
            self.assertEqual(gain["model_kind"],"local_tabular_Q_not_neural_transformer")
            self.assertEqual(gain["production_neural_parameters_updated"],0)
            self.assertFalse(training["promoted_to_production"])
            self.assertEqual(len(gain["complete_q_diff_digest"]),64)

    def test_invalid_limits_do_not_build_unbounded_worlds(self):
        with self.assertRaises(MultiFactorError):
            plan_multifactor_scenarios(self.source,max_scenarios=1000)
        with self.assertRaises(MultiFactorError):
            plan_multifactor_scenarios(self.source,interaction_order=6)
        with self.assertRaises(MultiFactorError):
            execute_multifactor_scenarios(self.source,steps=500)
        with self.assertRaises(MultiFactorError):
            execute_multifactor_scenarios(self.source,max_scenarios=200)


if __name__=="__main__":
    unittest.main()
