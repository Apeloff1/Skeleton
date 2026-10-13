"""Source-backed protection for sparse ecology and causal witnessed events.

These tests target physical outcomes which were formerly silently suppressed by
configurable event-rule cardinality or hidden by active-species scheduling.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene


class CrossFamilyCausalIntegrityTests(unittest.TestCase):
    def test_single_rule_preserves_discovery_eyewitness_and_real_reward(self):
        small = {
            "consequence_depth": 1, "quest_goal": 1, "npc_perception": 2,
            "memory_decay_ticks": 0, "quest_ttl": 80,
            "night_sight_penalty": 0, "event_rules": 1,
            "rule_bonus_modulus": 7, "ending_policy": "persistent",
        }
        large = {**small, "event_rules": 100}
        itinerary = ["south", "east", "collect:0", "speak:0",
                     "choose:0:support", "help:0", "resolve:0"]
        minimal = run_advanced_session("quest_director", small, itinerary)
        varied = run_advanced_session("quest_director", large, itinerary)
        self.assertTrue(verify_advanced_session(minimal, small))
        self.assertTrue(verify_advanced_session(varied, large))
        for report in (minimal, varied):
            world = report["state"]
            self.assertEqual(world["quests_completed"], 1)
            self.assertEqual(world["quests"][0]["origin_actor"], "player")
            self.assertEqual(world["quests"][0]["status"], "resolved")
            self.assertEqual(world["quests"][0]["testimonies"], [0])
            self.assertEqual(world["events_log"][0]["kind"], "discover")
            self.assertIn(0, world["events_log"][0]["direct_witnesses"])
        self.assertEqual(minimal["state"]["quests"][0]["rule_id"], 0)
        self.assertGreater(varied["state"]["quests"][0]["rule_id"], 0)
        self.assertNotEqual(minimal["state"]["gold"], varied["state"]["gold"])

    def test_compact_rules_never_award_phantom_choice_without_evidence(self):
        settings = {"event_rules": 1, "consequence_depth": 1}
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director", settings,
                                 ["choose:0:support"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director", settings,
                                 ["south", "east", "collect:0",
                                  "choose:0:support"])
        physically_witnessed = run_advanced_session(
            "quest_director", settings,
            ["south", "east", "collect:0", "speak:0"]
        )
        self.assertTrue(verify_advanced_session(physically_witnessed, settings))
        self.assertEqual(physically_witnessed["state"]["quests"][0]["testimonies"], [0])

    def test_sparse_distant_species_receive_due_finite_food_allocation(self):
        params = {"species": 500, "predators": 100, "cohort_period": 2}
        before = run_advanced_session("ecosystem", params)["state"]
        report = run_advanced_session("ecosystem", params, ["wait", "wait"])
        self.assertTrue(verify_advanced_session(report, params))
        state = report["state"]
        self.assertEqual(len(state["species"]), 80)
        self.assertEqual(state["dormant_species"], 420)
        self.assertEqual(state["background_batches"], 1)
        self.assertGreater(state["background_food_consumed"], 0)
        self.assertGreater(state["dormant_population"], 0)
        self.assertLessEqual(state["background_food_consumed"],
                             state["food_consumed"])
        self.assertEqual(
            state["births"], sum(x["births"] for x in state["species"])
            + state["background_births"]
        )
        self.assertEqual(
            state["deaths"], sum(x["deaths"] for x in state["species"])
            + state["background_deaths"]
        )
        for source, after in zip(before["habitats"], state["habitats"]):
            self.assertEqual(source["id"], after["id"])
            self.assertGreaterEqual(after["food"], 0)
            self.assertLessEqual(after["food"], after["capacity"])

    def test_sparse_cohort_phase_accounting_and_replay_rejects_forgery(self):
        params = {"species": 500, "predators": 100, "cohort_period": 2}
        actions = ["wait", "wait", "wait", "wait"]
        record = run_advanced_session("ecosystem", params, actions, seed=12)
        self.assertTrue(verify_advanced_session(record, params))
        self.assertEqual(record["state"]["background_batches"], 2)
        self.assertGreater(record["state"]["background_food_consumed"], 0)
        forged = deepcopy(record)
        forged["state"]["background_food_consumed"] += 1
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged, params)
        forged = deepcopy(record)
        forged["state"]["habitats"][0]["food"] += 1
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged, params)

    def test_rule_cardinality_does_not_create_source_gaps_between_seeds(self):
        settings = {"event_rules": 1, "consequence_depth": 1,
                    "npc_perception": 2, "night_sight_penalty": 0}
        for seed in (0, 1, 5, 9):
            with self.subTest(seed=seed):
                source = make_advanced_scene("quest_director", settings, seed=seed)
                result = run_advanced_session("quest_director", settings,
                                             ["south", "east", "collect:0"],
                                             seed=seed, scene=source)
                self.assertTrue(verify_advanced_session(result, settings))
                self.assertEqual(len(result["state"]["quests"]), 1)
                self.assertEqual(result["state"]["quests"][0]["rule_id"], 0)
                self.assertEqual(result["state"]["quests"][0]["origin_event"], 0)


if __name__ == "__main__":
    unittest.main()
