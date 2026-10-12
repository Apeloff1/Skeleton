"""Real, independently replayed counterfactual NPC event-order analysis."""
from __future__ import annotations

from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_interleaved_world as sources
from skeleton.ai.game_builder.advanced_interleaved_counterfactual import (
    MAX_SCENARIOS,OBJECTIVES,CounterfactualWorldError,
    run_interleaved_counterfactuals,verify_interleaved_counterfactuals,
)


class OriginalInterleavedMirrorTests(unittest.TestCase):
    @staticmethod
    def inputs():
        p,g,s,c=sources.OriginalInterleavedWorldTests.inputs()
        factory=sources.OriginalInterleavedWorldTests.timeline
        candidates=[
            {"name":"harvest_first","timeline":factory("genre","physical")},
            {"name":"collision_first","timeline":factory("physical","genre")},
        ]
        return p,g,s,c,candidates

    def test_same_actual_sources_different_order_changes_original_npc_event_origins(self):
        p,g,s,c,candidates=self.inputs()
        record=run_interleaved_counterfactuals(
            p,g,s,candidates,c,objective="direct_memories")
        self.assertEqual(record["scenario_count"],2)
        self.assertEqual(record["baseline_scenario"],"harvest_first")
        self.assertEqual(record["scenarios"][0]["difference_from_first"]
                         ["event_order_changed"],False)
        self.assertEqual(record["scenarios"][1]["difference_from_first"]
                         ["event_order_changed"],True)
        self.assertEqual(record["scenarios"][1]["difference_from_first"]
                         ["quest_origin_order_changed"],True)
        self.assertEqual([a["physical_event_count"] for a in record["scenarios"]],[1,1])
        self.assertEqual([a["genre_event_count"] for a in record["scenarios"]],[1,1])
        self.assertTrue(verify_interleaved_counterfactuals(
            record,p,g,s,candidates,c))

    def test_each_ranking_is_only_factually_defined_metric_not_generic_ai_better(self):
        p,g,s,c,scenarios=self.inputs()
        for metric in OBJECTIVES:
            with self.subTest(metric=metric):
                result=run_interleaved_counterfactuals(
                    p,g,s,scenarios,c,objective=metric)
                self.assertEqual(result["objective"],metric)
                self.assertFalse(result["universal_game_quality_claimed"])
                self.assertFalse(result["automatic_model_training_approved"])
                scores=[x["objective_score"] for x in result["scenarios"]]
                ranked=[x["objective_score"] for x in
                        result["ranking_for_this_metric_only"]]
                self.assertEqual(ranked,sorted(scores,reverse=True))
                self.assertTrue(verify_interleaved_counterfactuals(
                    result,p,g,s,scenarios,c))

    def test_determinism_of_proof_chains_and_independent_replay(self):
        p,g,s,c,variants=self.inputs()
        first=run_interleaved_counterfactuals(p,g,s,variants,c)
        again=run_interleaved_counterfactuals(p,g,s,variants,c)
        self.assertEqual(first,again)
        self.assertEqual(first["scenarios"][-1]["head_hash"],first["head_hash"])
        self.assertEqual(first["scenarios"][0]["difference_from_first"]
                         ["total_site_integrity"],0)
        self.assertTrue(first["digest"])

    def test_same_original_npc_action_multiset_is_required_for_fair_comparison(self):
        p,g,s,c,variants=self.inputs()
        first=deepcopy(variants)
        first[0]["timeline"].append({
            "at":2,"lane":"world","action":"wait"})
        with self.assertRaises(CounterfactualWorldError):
            run_interleaved_counterfactuals(p,g,s,first,c)
        two=deepcopy(variants)
        for candidate in two:
            candidate["timeline"].append({
                "at":2,"lane":"world","action":"wait"})
        result=run_interleaved_counterfactuals(p,g,s,two,c)
        self.assertEqual(result["scenarios"][0]["world_command_count"],1)
        self.assertEqual(result["scenarios"][1]["world_command_count"],1)

    def test_source_data_and_original_mutable_world_not_changed_by_scenario_lab(self):
        p,g,s,c,variants=self.inputs()
        original=deepcopy((p,g,s,c,variants))
        proof=run_interleaved_counterfactuals(p,g,s,variants,c)
        self.assertEqual((p,g,s,c,variants),original)
        self.assertFalse(proof["original_project_mutated"])
        self.assertFalse(proof["native_multi_engine_certified"])
        self.assertGreaterEqual(proof["scenarios"][0]["metric"]["active_quests"],1)

    def test_unearned_scenario_or_forged_metric_cannot_rewrite_ranked_original_world(self):
        p,g,s,c,variants=self.inputs()
        good=run_interleaved_counterfactuals(
            p,g,s,variants,c,objective="site_integrity")
        for alter in (
            lambda x:x["scenarios"][0].update(objective_score=999),
            lambda x:x["scenarios"][1]["metric"]["site_stock"].append(999),
            lambda x:x["scenarios"][0].update(head_hash="0"*64),
            lambda x:x["scenarios"][1]["difference_from_first"].update(
                direct_memories=900),
            lambda x:x["ranking_for_this_metric_only"][0].update(
                objective_score=123456),
            lambda x:x.update(automatic_model_training_approved=True),
            lambda x:x.update(universal_game_quality_claimed=True),
        ):
            forged=deepcopy(good);alter(forged)
            with self.assertRaises(CounterfactualWorldError):
                verify_interleaved_counterfactuals(forged,p,g,s,variants,c)

    def test_unreviewed_variant_shape_duplicate_name_metric_and_size_rejected(self):
        p,g,s,c,variants=self.inputs()
        invalid=(
            [],
            [variants[0]],
            variants+[variants[1]],
            [{"name":"INVALID","timeline":variants[0]["timeline"]},variants[1]],
            [{"name":"client gold","timeline":variants[0]["timeline"]},variants[1]],
            [{"name":True,"timeline":variants[0]["timeline"]},variants[1]],
            variants*4,
        )
        for value in invalid:
            with self.subTest(size=len(value)),self.assertRaises(CounterfactualWorldError):
                run_interleaved_counterfactuals(p,g,s,value,c)
        self.assertEqual(MAX_SCENARIOS,6)
        with self.assertRaises(CounterfactualWorldError):
            run_interleaved_counterfactuals(
                p,g,s,variants,c,objective="automatically_best_game")

    def test_original_genre_and_physics_source_forgery_cannot_produce_valid_mirror(self):
        p,g,s,c,variants=self.inputs()
        forged=deepcopy(g)
        forged[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(CounterfactualWorldError):
            run_interleaved_counterfactuals(p,forged,s,variants,c)
        bad_physics=deepcopy(p)
        bad_physics[0]["source_session"]["state"]["fuel"]=900
        with self.assertRaises(CounterfactualWorldError):
            run_interleaved_counterfactuals(bad_physics,g,s,variants,c)


if __name__=="__main__":
    unittest.main()
