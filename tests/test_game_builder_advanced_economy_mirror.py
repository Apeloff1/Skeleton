"""Rigorous original-economy strategy mirror: multiple worlds, actual outcomes."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_economy_mirror import (
    METRICS, PARETO_GOALS, EconomyMirrorError,
    analyze_original_economy, verify_original_economy_mirror,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene


class OriginalEconomyMirrorTests(unittest.TestCase):
    def test_multiple_competing_economic_scenarios_are_real_and_replay_proven(self):
        scene = make_advanced_scene("economy", seed=8)
        report = analyze_original_economy(scene, horizon=12)
        self.assertTrue(verify_original_economy_mirror(report, scene))
        self.assertGreaterEqual(report["scenarios_verified"], 6)
        self.assertEqual(report["scenarios_attempted"],
                         report["scenarios_verified"] + report["scenarios_infeasible"])
        self.assertIn("passive_reference", [r["strategy"] for r in report["evaluated"]])
        self.assertTrue(report["pareto_frontier"])
        self.assertIn(report["top_relative_policy"],
                      [r["strategy"] for r in report["evaluated"]])
        self.assertEqual(report["modeled_markets"], 8)
        self.assertFalse(report["weights_promoted"])
        self.assertFalse(report["production_release_certified"])
        self.assertFalse(report["complete_search_proved"])
        for item in report["evaluated"]:
            game = run_advanced_session("economy", actions=item["actions"],
                                        seed=8, scene=scene)
            self.assertTrue(verify_advanced_session(game))
            self.assertEqual(item["gameplay_session_digest"], game["digest"])
            self.assertEqual(item["gameplay_head_digest"], game["head_digest"])
            self.assertEqual(len(item["actions"]), 12)
            self.assertEqual(item["metrics"]["total_money"],
                             report["baseline_metrics"]["total_money"])
            self.assertEqual(set(item["metrics"]), set(METRICS))
            for key in METRICS:
                self.assertEqual(item["delta_vs_passive"][key],
                                 item["metrics"][key] - report["baseline_metrics"][key])

    def test_economy_mirror_never_claims_risk_free_profitable_trade(self):
        scene = make_advanced_scene("economy")
        report = analyze_original_economy(scene)
        deliveries = [r for r in report["evaluated"]
                      if r["strategy"] == "physical_import_delivery"]
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["metrics"]["imported_deliveries"], 1)
        self.assertLess(deliveries[0]["metrics"]["player_cash"],
                        report["baseline_metrics"]["player_cash"])
        self.assertEqual(deliveries[0]["metrics"]["total_money"],
                         report["baseline_metrics"]["total_money"])

    def test_competing_strategies_consume_real_goods_and_capital(self):
        scene = make_advanced_scene("economy", seed=5)
        report = analyze_original_economy(scene, horizon=12)
        candidates = {r["strategy"]: r for r in report["evaluated"]}
        self.assertIn("finite_regional_harvest", candidates)
        self.assertIn("material_conversion", candidates)
        self.assertIn("physical_import_delivery", candidates)
        harvest = candidates["finite_regional_harvest"]["metrics"]
        baseline = report["baseline_metrics"]
        self.assertGreater(harvest["market_inventory"], baseline["market_inventory"])
        self.assertLess(harvest["remaining_reserves"], baseline["remaining_reserves"])
        manufactured = candidates["material_conversion"]["metrics"]
        self.assertEqual(manufactured["manufactured_units"], 1)
        self.assertLess(manufactured["market_inventory"], baseline["market_inventory"])

    def test_parameter_sensitivity_source_custody_and_sparse_budget(self):
        compact = {"goods": 3, "market_nodes": 2, "starting_cash": 120}
        scene = make_advanced_scene("economy", compact, seed=37)
        report = analyze_original_economy(scene, compact, horizon=12,
                                           max_scenarios=40)
        self.assertEqual(report["modeled_markets"], 2)
        self.assertEqual(report["modeled_goods"], 3)
        self.assertTrue(verify_original_economy_mirror(report, scene, compact))
        bigger = {"goods": 500, "market_nodes": 100}
        source = make_advanced_scene("economy", bigger, seed=1)
        bounded = analyze_original_economy(source, bigger, horizon=4,
                                           max_scenarios=8)
        self.assertEqual(bounded["unmodeled_markets"], 92)
        self.assertEqual(bounded["unmodeled_goods"], 492)
        self.assertLessEqual(bounded["scenarios_attempted"], 8)
        self.assertTrue(verify_original_economy_mirror(bounded, source, bigger))

    def test_no_false_certification_under_an_insufficient_search_budget(self):
        scene = make_advanced_scene("economy")
        report = analyze_original_economy(scene, horizon=2, max_scenarios=1)
        self.assertEqual(report["scenarios_attempted"], 1)
        self.assertEqual(report["scenarios_verified"], 1)
        self.assertEqual(report["top_relative_policy"], "passive_reference")
        self.assertEqual(report["pareto_frontier"], ["passive_reference"])
        self.assertFalse(report["complete_search_proved"])
        self.assertTrue(verify_original_economy_mirror(report, scene))

    def test_pareto_frontier_uses_real_replay_objectives(self):
        scene = make_advanced_scene("economy")
        report = analyze_original_economy(scene, horizon=12)
        choices = {x["strategy"]: x for x in report["evaluated"]}
        for name in report["pareto_frontier"]:
            me = choices[name]["metrics"]
            for other_name, record in choices.items():
                if other_name == name:
                    continue
                you = record["metrics"]
                dominates = all(you[k] >= me[k] for k in PARETO_GOALS) and any(
                    you[k] > me[k] for k in PARETO_GOALS
                )
                self.assertFalse(dominates, (name, other_name))

    def test_forged_history_cash_score_and_source_refuse(self):
        scene = make_advanced_scene("economy", seed=11)
        report = analyze_original_economy(scene, max_scenarios=12)
        for mutate in (
            lambda x: x["evaluated"][0]["metrics"].__setitem__("player_cash", 1_000_000),
            lambda x: x["evaluated"][0].__setitem__("relative_policy_score", 999999),
            lambda x: x["evaluated"][0]["actions"].__setitem__(0, "retire"),
            lambda x: x.__setitem__("weights_promoted", True),
            lambda x: x.__setitem__("top_relative_policy", "guaranteed_profit"),
            lambda x: x.__setitem__("source_digest", "a" * 64),
            lambda x: x.__setitem__("digest", "0" * 64),
        ):
            copy = deepcopy(report)
            mutate(copy)
            with self.subTest(corrupt=mutate):
                with self.assertRaises(EconomyMirrorError):
                    verify_original_economy_mirror(copy, scene)
        other = make_advanced_scene("economy", seed=12)
        with self.assertRaises(EconomyMirrorError):
            verify_original_economy_mirror(report, other)

    def test_budgets_are_exact_and_bounded(self):
        scene = make_advanced_scene("economy")
        for options in (
            {"horizon": 0}, {"horizon": 49}, {"horizon": True},
            {"max_scenarios": 0}, {"max_scenarios": 41},
            {"max_scenarios": True}, {"horizon": 1.5},
        ):
            with self.subTest(options=options):
                with self.assertRaises(EconomyMirrorError):
                    analyze_original_economy(scene, **options)


if __name__ == "__main__":
    unittest.main()
