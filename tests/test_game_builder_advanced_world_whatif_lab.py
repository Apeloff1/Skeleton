"""Adversarial original world alternative ordering with independent source replay."""
from __future__ import annotations

from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_interleaved_world as fixtures
from skeleton.ai.game_builder.advanced_interleaved_world import (
    run_interleaved_world,
)
from skeleton.ai.game_builder.advanced_world_whatif_lab import (
    SCHEMA,OBJECTIVES,MAX_ATTEMPTS,WorldWhatIfError,
    run_world_whatif,verify_world_whatif,
)


class RealCausalWhatIfTests(unittest.TestCase):
    @staticmethod
    def input():
        physical,genres,scene,cfg=fixtures.OriginalInterleavedWorldTests.inputs()
        timeline=fixtures.OriginalInterleavedWorldTests.timeline(
            "physical","world","genre","world")
        return physical,genres,scene,cfg,timeline

    def test_real_counterfactual_swaps_physically_verified_game_event_order(self):
        p,g,scene,cfg,schedule=self.input()
        original=deepcopy((p,g,scene,cfg,schedule))
        proof=run_world_whatif(
            p,g,scene,schedule,cfg,max_depth=2,max_attempts=16,max_accepted=8)
        self.assertEqual(proof["schema"],SCHEMA)
        self.assertEqual((p,g,scene,cfg,schedule),original)
        self.assertGreater(proof["attempted_permutations"],0)
        self.assertGreater(proof["accepted_count"],0)
        self.assertLessEqual(proof["accepted_count"],8)
        self.assertEqual(proof["baseline"]["metrics"]["world_tick"],4)
        self.assertTrue(all(row["actually_replayed"]
                            for row in proof["accepted_scenarios"]))
        self.assertTrue(verify_world_whatif(
            proof,p,g,scene,schedule,cfg))

    def test_selected_scenario_proves_the_exact_original_world_causes(self):
        p,g,scene,cfg,schedule=self.input()
        proof=run_world_whatif(p,g,scene,schedule,cfg,
                               max_depth=2,max_attempts=12)
        for scenario in proof["accepted_scenarios"]:
            actual=run_interleaved_world(
                p,g,scene,scenario["timeline"],cfg)
            self.assertEqual(actual["digest"],scenario["campaign_digest"])
            self.assertEqual(actual["head_hash"],
                             scenario["source_evidence"]["original_head_hash"])
            self.assertEqual(actual["world_state"]["tick"],
                             scenario["metrics"]["world_tick"])
            self.assertEqual(len(scenario["source_evidence"]
                                 ["event_origin_order"]),len(schedule))
            self.assertEqual(
                [r["original_event_id"] for r in scenario["source_evidence"]
                 ["event_origin_order"] if r["lane"]!="world"],
                [row["source"]["world_event_id"] for row in actual["timeline"]
                 if row["lane"]!="world"])

    def test_world_npc_metrics_are_actual_numbers_not_language_model_claims(self):
        p,g,scene,cfg,schedule=self.input()
        report=run_world_whatif(
            p,g,scene,schedule,cfg,objective="community_recovery")
        self.assertIn("site_integrity",report["baseline"]["metrics"])
        self.assertIn("direct_memories",report["baseline"]["metrics"])
        self.assertIn("rumor_memories",report["baseline"]["metrics"])
        self.assertIn("quests_completed",report["baseline"]["metrics"])
        for alt in report["accepted_scenarios"]:
            for name,delta in alt["delta_from_baseline"].items():
                self.assertEqual(
                    delta,alt["metrics"][name]-report["baseline"]["metrics"][name])
            self.assertFalse(alt["native_certification_claim"])
        self.assertFalse(report["automatic_ai_weight_promotion"])
        self.assertFalse(report["automatic_authoring_committed"])
        self.assertFalse(report["hardware_certified"])

    def test_all_four_explicit_priority_lenses_produce_replayable_results(self):
        p,g,scene,cfg,schedule=self.input()
        for objective in OBJECTIVES:
            with self.subTest(objective=objective):
                report=run_world_whatif(
                    p,g,scene,schedule,cfg,objective=objective,
                    max_depth=1,max_attempts=4,max_accepted=2)
                self.assertEqual(report["objective"],objective)
                self.assertTrue(verify_world_whatif(
                    report,p,g,scene,schedule,cfg))

    def test_zero_improvement_never_misreported_as_model_or_world_better(self):
        p,g,scene,cfg,schedule=self.input()
        report=run_world_whatif(p,g,scene,schedule,cfg,max_depth=1,
                                max_attempts=4,max_accepted=4)
        chosen=next((row for row in report["accepted_scenarios"]
                     if row["scenario_id"]==report["selected_scenario_id"]),None)
        self.assertEqual(
            report["selected_is_measurably_better_than_baseline"],
            bool(chosen and chosen["objective_score"]>
                 report["baseline"]["objective_score"]))
        self.assertFalse(report["automatic_ai_weight_promotion"])

    def test_bounded_adversarial_search_is_repeatable_and_breadth_first(self):
        p,g,scene,cfg,schedule=self.input()
        first=run_world_whatif(p,g,scene,schedule,cfg,max_depth=3,
                               max_attempts=12,max_accepted=6)
        again=run_world_whatif(p,g,scene,schedule,cfg,max_depth=3,
                               max_attempts=12,max_accepted=6)
        self.assertEqual(first,again)
        self.assertLessEqual(first["attempted_permutations"],12)
        self.assertLessEqual(first["accepted_count"],6)
        self.assertTrue(all(1<=x["depth"]<=3 for x in first["accepted_scenarios"]))
        self.assertEqual(first["accepted_count"]+first["rejected_count"],
                         first["attempted_permutations"])

    def test_malformed_objective_depth_attempt_budget_and_boolean_inputs_fail(self):
        p,g,scene,cfg,schedule=self.input()
        for value in ("omniscient_best","publication",None,[],0):
            with self.subTest(value=str(value)),self.assertRaises(WorldWhatIfError):
                run_world_whatif(p,g,scene,schedule,cfg,objective=value)
        for settings in (
            {"max_depth":0},{"max_depth":True},{"max_depth":99},
            {"max_attempts":0},{"max_attempts":MAX_ATTEMPTS+1},
            {"max_attempts":True},{"max_accepted":0},
            {"max_accepted":True},{"max_accepted":100},
        ):
            with self.subTest(settings=settings),self.assertRaises(WorldWhatIfError):
                run_world_whatif(p,g,scene,schedule,cfg,**settings)

    def test_unsourced_gameplay_and_missing_real_events_cannot_seed_experiment(self):
        p,g,scene,cfg,schedule=self.input()
        for actions in (
            schedule[:2],  # omit the required authenticated genre source event
            [dict(schedule[0],at=5)]+deepcopy(schedule[1:]),
            [dict(schedule[0],lane="mint_gold")]+deepcopy(schedule[1:]),
        ):
            with self.assertRaises(WorldWhatIfError):
                run_world_whatif(p,g,scene,actions,cfg)
        source=deepcopy(g)
        source[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(WorldWhatIfError):
            run_world_whatif(p,source,scene,schedule,cfg)

    def test_forged_rankings_metrics_and_source_identity_fail_full_verifier(self):
        p,g,scene,cfg,schedule=self.input()
        true=run_world_whatif(p,g,scene,schedule,cfg,max_depth=2)
        cases=(
            lambda x:x["baseline"]["metrics"].update(gold=999),
            lambda x:x["accepted_scenarios"][0]["metrics"].update(
                     direct_memories=999),
            lambda x:x["accepted_scenarios"][0].update(
                     outperforms_baseline_on_selected_objective=True),
            lambda x:x["accepted_scenarios"][0]["source_evidence"]
                     ["event_origin_order"][0].update(source_receipt="bad"),
            lambda x:x.update(selected_scenario_id="attacker"),
            lambda x:x.update(automatic_authoring_committed=True),
            lambda x:x.update(digest="0"*64),
        )
        self.assertTrue(true["accepted_scenarios"])
        for mutate in cases:
            altered=deepcopy(true);mutate(altered)
            with self.assertRaises(WorldWhatIfError):
                verify_world_whatif(altered,p,g,scene,schedule,cfg)

    def test_original_npc_memory_and_quest_source_are_not_adversarially_invented(self):
        p,g,scene,cfg,schedule=self.input()
        result=run_world_whatif(
            p,g,scene,schedule,cfg,max_depth=2)
        for candidate in result["accepted_scenarios"]:
            real=run_interleaved_world(p,g,scene,candidate["timeline"],cfg)
            actual=real["world_state"]
            self.assertEqual(
                candidate["metrics"]["direct_memories"],
                sum(len(n["memories"]) for n in actual["npcs"]))
            self.assertEqual(
                candidate["metrics"]["quests_completed"],
                actual["quests_completed"])
            for event in candidate["source_evidence"]["event_origin_order"]:
                if event["lane"] in ("physical","genre"):
                    self.assertIsInstance(event["source_receipt"],str)
                    self.assertTrue(event["original_event_id"] is not None)

    def test_time_costs_are_source_true_not_event_index_guesses(self):
        p,g,scene,cfg,schedule=self.input()
        schedule[1]["action"]="wait:4"
        # Real wait:4 advances more than one canonical tick; later original
        # source action admissions must preserve their actual event clock.
        schedule[2]["at"]=5
        schedule[3]["at"]=6
        authentic=run_interleaved_world(p,g,scene,schedule,cfg)
        report=run_world_whatif(p,g,scene,schedule,cfg,max_depth=1,
                                max_attempts=5)
        self.assertEqual(authentic["world_state"]["tick"],7)
        self.assertEqual(report["baseline"]["metrics"]["world_tick"],7)
        for alternate in report["accepted_scenarios"]:
            self.assertEqual(
                alternate["metrics"]["world_tick"],7)
            self.assertTrue(verify_world_whatif(
                report,p,g,scene,schedule,cfg))


if __name__=="__main__":
    unittest.main()
