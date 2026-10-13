"""Independent adversarial comparison of real cross-engine causal NPC worlds."""
from __future__ import annotations
from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_interleaved_world as fixtures
from skeleton.ai.game_builder.advanced_interleaved_counterfactual import (
    SCHEMA,MAX_CANDIDATES,CounterfactualWorldError,
    run_counterfactual_lab,verify_counterfactual_lab,
)


class OriginalCounterfactualGameWorldTests(unittest.TestCase):
    @staticmethod
    def sources(*,genre="farming"):
        return fixtures.OriginalInterleavedWorldTests.inputs(genre=genre)

    @staticmethod
    def timeline(*lanes):
        return fixtures.OriginalInterleavedWorldTests.timeline(*lanes)

    def test_adversarial_lab_truly_reexecutes_alternate_source_game_causality(self):
        p,g,s,c=self.sources()
        t=self.timeline("physical","genre")
        old=deepcopy((p,g,s,c,t))
        report=run_counterfactual_lab(p,g,s,t,c)
        self.assertEqual((p,g,s,c,t),old)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["total_trials"],1)
        self.assertEqual(report["valid_replayed_trials"],1)
        self.assertEqual(report["invalid_trials"],0)
        candidate=report["candidates"][0]
        self.assertTrue(candidate["valid"])
        self.assertEqual([x["lane"] for x in candidate["authored_timeline"]],
                         ["genre","physical"])
        self.assertEqual(candidate["changed_dimensions"],
                         sorted(candidate["verified_deltas"]))
        self.assertIn("event_origins",candidate["changed_dimensions"])
        self.assertEqual(candidate["baseline_digest"],report["baseline_campaign_digest"])
        self.assertTrue(verify_counterfactual_lab(report,p,g,s,t,c))

    def test_what_if_timeline_changes_are_source_bound_not_decorative(self):
        p,g,s,c=self.sources()
        t=self.timeline("physical","world","genre","world")
        report=run_counterfactual_lab(p,g,s,t,c,max_candidates=3)
        self.assertEqual(report["total_trials"],3)
        self.assertGreaterEqual(report["valid_replayed_trials"],1)
        self.assertGreaterEqual(report["causally_changed_trials"],1)
        self.assertTrue(all(candidate["strategy"]=="adjacent_causal_swap"
                            for candidate in report["candidates"]))
        self.assertTrue(verify_counterfactual_lab(report,p,g,s,t,c))

    def test_original_maritime_shipment_is_not_arbitrarily_minted_by_swap(self):
        p,g,s,c=self.sources(genre="sailing")
        t=self.timeline("physical","genre")
        from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
        layout=deepcopy(s["layout"])
        layout["sites"][1]["stock"]=0
        s=make_advanced_scene("quest_director",c,seed=0,layout=layout)
        report=run_counterfactual_lab(p,g,s,t,c)
        self.assertEqual(report["valid_replayed_trials"],1)
        self.assertEqual(report["baseline_snapshot"]["site_stock"][1],1)
        self.assertNotIn("site_stock",report["candidates"][0]["changed_dimensions"])
        self.assertFalse(report["source_game_files_modified"])
        self.assertFalse(report["unearned_world_rewards_applied"])

    def test_unverified_invalid_variant_must_never_be_counted_as_improvement(self):
        p,g,s,c=self.sources()
        t=self.timeline("physical","world","genre")
        report=run_counterfactual_lab(p,g,s,t,c)
        self.assertEqual(report["valid_replayed_trials"]+
                         report["invalid_trials"],report["total_trials"])
        self.assertTrue(all(candidate["changed_dimension_count"]==0
                            for candidate in report["candidates"] if not candidate["valid"]))
        self.assertTrue(all(candidate["candidate_digest"] is None
                            for candidate in report["candidates"] if not candidate["valid"]))

    def test_alternative_world_clock_recomputes_actual_npc_memory_not_fake_deltas(self):
        p,g,s,c=self.sources()
        t=self.timeline("genre","physical","world")
        result=run_counterfactual_lab(p,g,s,t,c,max_candidates=2)
        self.assertEqual(result["total_trials"],2)
        self.assertGreaterEqual(result["valid_replayed_trials"],1)
        for candidate in result["candidates"]:
            if candidate["valid"]:
                self.assertEqual(candidate["outcome"],
                                 "independently_replayed_source_world")
                self.assertEqual(candidate["changed_dimension_count"],
                                 len(candidate["changed_dimensions"]))
                self.assertEqual(candidate["actual_world_tick"],3)
                self.assertNotEqual(candidate["candidate_digest"],None)

    def test_bounded_trial_and_timeline_input_validation(self):
        p,g,s,c=self.sources()
        t=self.timeline("genre","physical")
        for n in (True,0,-1,MAX_CANDIDATES+1,1.5):
            with self.subTest(n=n),self.assertRaises(CounterfactualWorldError):
                run_counterfactual_lab(p,g,s,t,c,max_candidates=n)
        for tbad in ([],[{"at":0,"lane":"physical","source_index":0,"event_index":0}]):
            with self.assertRaises(CounterfactualWorldError):
                run_counterfactual_lab(p,g,s,tbad,c)

    def test_session_state_attack_fails_independent_counterfactual_validation(self):
        p,g,s,c=self.sources()
        t=self.timeline("physical","genre")
        good=run_counterfactual_lab(p,g,s,t,c)
        altered=deepcopy(g)
        altered[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(CounterfactualWorldError):
            run_counterfactual_lab(p,altered,s,t,c)
        with self.assertRaises(CounterfactualWorldError):
            verify_counterfactual_lab(good,p,altered,s,t,c)

    def test_client_forged_positive_causal_scoring_is_rejected(self):
        p,g,s,c=self.sources()
        t=self.timeline("physical","genre")
        honest=run_counterfactual_lab(p,g,s,t,c)
        alters=(
            lambda x:x["candidates"][0].update(changed_dimension_count=999),
            lambda x:x["candidates"][0]["verified_deltas"].update(
                       player_resources={"baseline":{"gold":0},
                                         "counterfactual":{"gold":999}}),
            lambda x:x["candidates"][0].update(candidate_digest="0"*64),
            lambda x:x["candidates"][0].update(head_hash="0"*64),
            lambda x:x.update(causally_changed_trials=999),
            lambda x:x.update(automatic_ai_weight_promotion=True),
        )
        for alter in alters:
            corrupt=deepcopy(honest)
            alter(corrupt)
            with self.assertRaises(CounterfactualWorldError):
                verify_counterfactual_lab(corrupt,p,g,s,t,c)

    def test_real_world_terminal_and_memory_decay_rules_remain_authoritative(self):
        p,g,s,c=self.sources()
        c["memory_decay_ticks"]=1
        s=__import__(
            "skeleton.ai.game_builder.advanced_level_scenes",
            fromlist=["make_advanced_scene"]).make_advanced_scene(
            "quest_director",c,seed=0)
        t=self.timeline("physical","genre","world")
        result=run_counterfactual_lab(p,g,s,t,c)
        self.assertEqual(result["baseline_world_tick"],3)
        self.assertEqual(result["baseline_snapshot"]["world_time"],3)
        self.assertTrue(verify_counterfactual_lab(result,p,g,s,t,c))


if __name__=="__main__":
    unittest.main()
