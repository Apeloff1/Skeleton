"""Source-replayed counterfactuals: same earned inputs, different true NPC worlds."""
from __future__ import annotations

from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_interleaved_world as fixtures
from skeleton.ai.game_builder.advanced_world_whatif_pareto import (
    WorldWhatIfError,AXES,MAX_SCENARIOS,
    run_world_whatif_lab,verify_world_whatif_lab,
)


class OriginalWorldWhatIfTests(unittest.TestCase):
    @staticmethod
    def sources(genre="farming"):
        return fixtures.OriginalInterleavedWorldTests.inputs(genre=genre)

    @staticmethod
    def plans():
        factory=fixtures.OriginalInterleavedWorldTests
        return [
            {"id":"genre_first","timeline":factory.timeline(
                "genre","world","physical","world")},
            {"id":"impact_first","timeline":factory.timeline(
                "physical","world","genre","world")},
        ]

    def test_two_actual_game_event_orders_produce_distinct_witness_histories(self):
        physical,genre,world,cfg=self.sources()
        original=deepcopy((physical,genre,world,cfg))
        schedules=self.plans()
        report=run_world_whatif_lab(physical,genre,world,schedules,cfg)
        self.assertEqual((physical,genre,world,cfg),original)
        self.assertEqual(report["baseline_id"],"genre_first")
        self.assertEqual(len(report["scenarios"]),2)
        self.assertNotEqual(report["scenarios"][0]["world_receipt_digest"],
                            report["scenarios"][1]["world_receipt_digest"])
        self.assertEqual(report["scenarios"][0]["metrics"]["world_tick"],4)
        self.assertEqual(report["scenarios"][1]["metrics"]["world_tick"],4)
        self.assertEqual(report["scenarios"][0]["metrics"]["physical_events"],1)
        self.assertEqual(report["scenarios"][1]["metrics"]["genre_events"],1)
        self.assertTrue(report["scenarios"][1]["changed_world_event_order"])
        self.assertNotEqual(report["scenarios"][0]["world_event_origins"],
                            report["scenarios"][1]["world_event_origins"])
        self.assertTrue(verify_world_whatif_lab(
            report,physical,genre,world,schedules,cfg))

    def test_same_actions_same_genre_sources_and_origin_ids_are_mandatory(self):
        physical,genre,world,cfg=self.sources()
        cases=(
            [{"id":"a","timeline":self.plans()[0]["timeline"]},
             {"id":"b","timeline":fixtures.OriginalInterleavedWorldTests.timeline(
                 "genre","physical")}],
            [{"id":"a","timeline":self.plans()[0]["timeline"]},
             {"id":"b","timeline":fixtures.OriginalInterleavedWorldTests.timeline(
                 "genre","world","physical","world","world")}],
            [{"id":"a","timeline":self.plans()[0]["timeline"]},
             {"id":"b","timeline":fixtures.OriginalInterleavedWorldTests.timeline(
                 "physical","world","genre","inspect")}],
        )
        for scenarios in cases:
            with self.subTest(scenarios=scenarios),self.assertRaises(WorldWhatIfError):
                run_world_whatif_lab(physical,genre,world,scenarios,cfg)

    def test_duplicate_schedules_differently_named_cannot_fake_replication(self):
        physical,genre,world,cfg=self.sources()
        timeline=self.plans()[0]["timeline"]
        with self.assertRaises(WorldWhatIfError):
            run_world_whatif_lab(physical,genre,world,[
                {"id":"first","timeline":timeline},
                {"id":"second","timeline":deepcopy(timeline)},
            ],cfg)

    def test_incompletely_scheduled_real_achievement_fails_even_if_comparator_accepts_input(self):
        physical,genre,world,cfg=self.sources()
        base=self.plans()
        base[1]["timeline"]=base[1]["timeline"][:3]
        with self.assertRaises(WorldWhatIfError):
            run_world_whatif_lab(physical,genre,world,base,cfg)

    def test_whatif_never_conflates_npc_rumor_with_firsthand_knowledge(self):
        physical,genre,world,cfg=self.sources()
        schedules=self.plans()
        report=run_world_whatif_lab(physical,genre,world,schedules,cfg,
                                   axes=("firsthand_memories","trust_total"))
        self.assertEqual(report["selected_axes"],["firsthand_memories","trust_total"])
        for row in report["scenarios"]:
            self.assertIn("rumor_records",row["metrics"])
            self.assertIn("firsthand_memories",row["metrics"])
            self.assertNotIn("rumor_records",report["selected_axes"])
            self.assertEqual(row["metrics"]["physical_events"],1)
            self.assertEqual(row["metrics"]["genre_events"],1)
        self.assertTrue(verify_world_whatif_lab(
            report,physical,genre,world,schedules,cfg))

    def test_sailing_stock_and_aircraft_achievement_are_real_whatif_facts(self):
        for source_name in ("sailing","flight"):
            with self.subTest(engine=source_name):
                physical,genre,world,cfg=self.sources(source_name)
                schedules=self.plans()
                report=run_world_whatif_lab(physical,genre,world,schedules,cfg)
                self.assertEqual(report["authoritative_source_session_count"],2)
                self.assertEqual(
                    [row["metrics"]["world_tick"] for row in report["scenarios"]],
                    [4,4])
                self.assertTrue(verify_world_whatif_lab(
                    report,physical,genre,world,schedules,cfg))

    def test_typed_bounded_objectives_cannot_mint_unsupported_improvements(self):
        physical,genre,world,cfg=self.sources()
        for axes in (
            ("winner_score",),("gold",),(True,),("quests_completed",True),
            ("quests_completed","quests_completed"),(),
            AXES+("invented_model_gain",)
        ):
            with self.subTest(axes=axes),self.assertRaises(WorldWhatIfError):
                run_world_whatif_lab(physical,genre,world,self.plans(),cfg,axes=axes)
        self.assertEqual(MAX_SCENARIOS,8)
        self.assertFalse(
            run_world_whatif_lab(physical,genre,world,self.plans(),cfg)
            ["automatic_model_training_approved"])

    def test_eight_scenarios_bound_and_same_id_denial(self):
        physical,genre,world,cfg=self.sources()
        base=self.plans()
        for wrong in (
            [],
            [base[0]],
            [{"id":"same","timeline":base[0]["timeline"]},
             {"id":"same","timeline":base[1]["timeline"]}],
            base*5,
            [{"id":"illegal label","timeline":base[0]["timeline"]},base[1]]
        ):
            with self.assertRaises(WorldWhatIfError):
                run_world_whatif_lab(physical,genre,world,wrong,cfg)

    def test_tampered_causal_world_metrics_or_pareto_claims_fail_complete_replay(self):
        physical,genre,world,cfg=self.sources()
        scenarios=self.plans()
        good=run_world_whatif_lab(physical,genre,world,scenarios,cfg)
        changes=(
            lambda v:v["scenarios"][0]["metrics"].update(player_gold=999),
            lambda v:v["scenarios"][1]["delta_from_baseline"].update(
                firsthand_memories=500),
            lambda v:v["scenarios"][0]["world_event_origins"][0].update(
                direct_witnesses=[999]),
            lambda v:v["scenarios"][0].update(
                world_receipt_digest="0"*64),
            lambda v:v["pareto_frontier_indices"].clear(),
            lambda v:v.update(automatic_model_training_approved=True),
            lambda v:v.update(strict_baseline_dominators=[1]),
        )
        for alter in changes:
            forged=deepcopy(good);alter(forged)
            if forged==good:
                # A no-op is not a forgery: choose an unambiguously false
                # Pareto witness in that unusual case.
                forged["strict_baseline_dominators"]=[42]
            with self.assertRaises(WorldWhatIfError):
                verify_world_whatif_lab(forged,physical,genre,world,scenarios,cfg)

    def test_source_authentication_prevents_counterfactual_world_money_from_forged_genre_game(self):
        physical,genre,world,cfg=self.sources()
        modified=deepcopy(genre)
        modified[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(WorldWhatIfError):
            run_world_whatif_lab(physical,modified,world,self.plans(),cfg)

    def test_baseline_and_alternates_do_not_change_original_source_input(self):
        physical,genre,world,cfg=self.sources()
        schedules=self.plans()
        initial=deepcopy((physical,genre,world,cfg,schedules))
        report=run_world_whatif_lab(physical,genre,world,schedules,cfg)
        self.assertEqual((physical,genre,world,cfg,schedules),initial)
        self.assertTrue(report["same_source_and_action_inputs"])
        self.assertTrue(report["comparison_has_no_automatic_winner"])
        self.assertTrue(report["original_game_saves_unchanged"])
        self.assertFalse(report["native_full_campaign_certified"])


if __name__=="__main__":
    unittest.main()
