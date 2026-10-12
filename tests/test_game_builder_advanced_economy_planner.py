"""Source-verified bounded trade planner cannot grant forged economic outcomes."""
import copy
import unittest

from skeleton.ai.game_builder.advanced_economy_planner import (
    EconomyPlanningError, plan_original_trade, verify_original_trade_plan,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)


class EconomyDirectorTests(unittest.TestCase):
    def test_planner_evolves_real_trade_and_mirrors_it(self):
        scene = make_advanced_scene("economy", seed=12)
        report = plan_original_trade(scene)
        self.assertEqual(report["status"], "replay_verified_trade")
        self.assertEqual(report["imported_deliveries"], 1)
        self.assertEqual(report["manufactured_units"], 1)
        self.assertEqual(report["verified_audits"], [0, 1])
        self.assertTrue(report["still_playable"])
        self.assertTrue(report["independent_replay_verified"])
        self.assertTrue(verify_original_trade_plan(report, scene))
        replay = run_advanced_session("economy", actions=report["actions"],
                                      scene=scene, seed=12)
        self.assertTrue(verify_advanced_session(replay))
        self.assertEqual(report["replay_digest"], replay["digest"])
        self.assertEqual(report["final_cash"], replay["state"]["cash"])

    def test_retirement_follows_actual_checkpoint(self):
        scene = make_advanced_scene("economy", seed=2)
        report = plan_original_trade(scene, retire=True)
        self.assertEqual(report["status"], "replay_verified_trade")
        self.assertTrue(report["retired"])
        self.assertFalse(report["still_playable"])
        self.assertTrue(verify_original_trade_plan(report, scene))

    def test_insufficient_action_budget_is_explicitly_inconclusive(self):
        scene = make_advanced_scene("economy", seed=2)
        report = plan_original_trade(scene, max_actions=3)
        self.assertEqual(report["status"], "inconclusive_bounded_trade")
        self.assertEqual(report["actions"], [])
        self.assertGreater(len(report["best_partial_actions"]), 0)
        self.assertFalse(report["independent_replay_verified"])
        self.assertTrue(verify_original_trade_plan(report, scene))

    def test_trade_never_mints_insufficient_source_material(self):
        scene = make_advanced_scene("economy")
        amended = copy.deepcopy(scene["layout"])
        amended["markets"][0]["inventory"][1] = 0
        amended_scene = make_advanced_scene("economy", layout=amended)
        result = plan_original_trade(amended_scene)
        self.assertEqual(result["status"], "inconclusive_bounded_trade")
        self.assertEqual(result["best_partial_imports"], 0)
        self.assertFalse(result["independent_replay_verified"])

    def test_longer_authored_delivery_objective_reports_resource_exhaustion(self):
        scene = make_advanced_scene("economy")
        amended = copy.deepcopy(scene["layout"])
        amended["trade_goal"] = 16
        amended_scene = make_advanced_scene("economy", layout=amended)
        report = plan_original_trade(amended_scene)
        self.assertIn(report["status"], ("inconclusive_bounded_trade",
                                         "replay_verified_trade"))
        if report["status"] == "replay_verified_trade":
            self.assertGreaterEqual(report["imported_deliveries"], 16)
        else:
            self.assertFalse(report["independent_replay_verified"])

    def test_no_forged_plan_fields_or_bypass_replay(self):
        scene = make_advanced_scene("economy")
        original = plan_original_trade(scene)
        for method in (
            lambda x: x.__setitem__("imported_deliveries", 900),
            lambda x: x.__setitem__("final_cash", 999999),
            lambda x: x["actions"].__setitem__(1, "wait"),
            lambda x: x.__setitem__("source_digest", "0" * 64),
            lambda x: x.__setitem__("independent_replay_verified", False),
        ):
            forged = copy.deepcopy(original)
            method(forged)
            with self.assertRaises(EconomyPlanningError):
                verify_original_trade_plan(forged, scene)

    def test_exact_budget_bounds_and_types(self):
        scene = make_advanced_scene("economy")
        for kwargs in ({"max_actions": 0}, {"max_actions": 129},
                       {"max_actions": True}, {"retire": 1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(EconomyPlanningError):
                    plan_original_trade(scene, **kwargs)


if __name__ == "__main__":
    unittest.main()
