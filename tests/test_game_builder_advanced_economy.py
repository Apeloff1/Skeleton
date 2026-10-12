"""End-to-end original economy engine: real stock, routes and replay custody."""
import copy
import unittest

from skeleton.ai.game_builder.system_editors import (
    make_editor_document, editor_spec, SystemEditorError,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene, validate_advanced_scene, SceneError,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)

ROUTE = [
    "audit", "manufacture", "harvest", "focus:2", "buy",
    "travel:1", "audit", "sell", "checkpoint",
]


def cash_total(state):
    return state["cash"] + sum(
        node["treasury"] + node["household_cash"] for node in state["markets"]
    )


def stock_total(state):
    return sum(sum(node["inventory"]) for node in state["markets"]) + sum(
        state["cargo"]
    )


class EconomyReferenceTests(unittest.TestCase):
    def test_editor_and_source_scene_are_advanced_and_strict(self):
        self.assertIn("economy", ENGINES)
        self.assertEqual(editor_spec("economy")["runtime_maturity"],
                         "advanced_reference_runtime")
        scene = make_advanced_scene("economy", seed=7)
        self.assertEqual(validate_advanced_scene(scene), scene)
        self.assertEqual(scene["editor"], "economy")
        self.assertEqual(len(scene["layout"]["markets"]), 8)
        game = run_advanced_session("economy", scene=scene, seed=7)
        self.assertTrue(verify_advanced_session(game))

    def test_real_market_path_and_nonterminal_checkpoint(self):
        scene = make_advanced_scene("economy", seed=3)
        proof = run_advanced_session("economy", actions=ROUTE, scene=scene, seed=3)
        state = proof["state"]
        self.assertTrue(state["checkpoint"])
        self.assertFalse(state["finished"])
        self.assertFalse(proof["terminal"])
        self.assertEqual(state["manufactured"], 1)
        self.assertGreater(state["harvested"], 0)
        self.assertEqual(state["imports_sold"], 1)
        self.assertEqual(state["transfers"], 1)
        self.assertEqual(state["audited"], [0, 1])
        self.assertEqual(proof["validated_turn_count"], len(ROUTE))
        self.assertTrue(verify_advanced_session(proof))
        self.assertNotEqual(proof["trace"][0]["digest"],
                            proof["trace"][-1]["digest"])
        retired = run_advanced_session("economy", actions=ROUTE + ["retire"])
        self.assertTrue(retired["terminal"])
        self.assertTrue(retired["state"]["retired"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("economy", actions=ROUTE + ["retire", "wait"])

    def test_cash_custody_has_no_external_minting(self):
        start = run_advanced_session("economy")["state"]
        after = run_advanced_session("economy", actions=[
            "harvest", "manufacture", "focus:0", "buy", "travel:1",
            "sell", "relief", "wait",
        ])["state"]
        self.assertEqual(cash_total(start), cash_total(after))
        self.assertGreater(after["household_consumed"], 0)
        self.assertGreater(after["household_spend"], 0)

    def test_material_stock_balance_tracks_harvest_manufacture_and_consumption(self):
        first = run_advanced_session("economy")["state"]
        end = run_advanced_session("economy", actions=[
            "harvest", "manufacture", "wait", "focus:2", "buy",
            "travel:1", "sell", "wait",
        ])["state"]
        ore_per_tool = make_editor_document("economy")["settings"]["ore_per_tool"]
        expected = (stock_total(first) + end["harvested"] +
                    end["manufactured"] * (1 - ore_per_tool) -
                    end["household_consumed"])
        self.assertEqual(stock_total(end), expected)
        self.assertEqual(end["manufactured"], 1)

    def test_market_prices_react_to_finite_demand(self):
        a = run_advanced_session("economy", actions=[])
        b = run_advanced_session("economy", actions=["wait"] * 12)
        self.assertNotEqual(a["state"]["markets"][0]["prices"],
                            b["state"]["markets"][0]["prices"])
        for node in b["state"]["markets"]:
            for value in node["prices"]:
                self.assertGreaterEqual(value, 1)
                self.assertLessEqual(value, 80)

    def test_import_credit_bound_to_each_unit_not_last_purchased_origin(self):
        run = run_advanced_session("economy", actions=[
            "buy", "travel:1", "buy", "sell", "sell",
        ])
        self.assertEqual(run["state"]["imports_sold"], 1)
        self.assertEqual(run["state"]["cargo"][0], 0)
        self.assertEqual(run["state"]["cargo_lots"][0], [])

    def test_no_free_repeat_credits_from_same_market_arbitrage(self):
        before = run_advanced_session("economy")["state"]
        loop = run_advanced_session("economy", actions=["buy", "sell"])
        self.assertLess(loop["state"]["cash"], before["cash"])
        self.assertEqual(loop["state"]["imports_sold"], 0)

    def test_finite_market_travel_and_absent_stock_fail_closed(self):
        for actions in (
            ["travel:2"], ["travel:15"], ["focus:15"],
            ["sell"], ["checkpoint"], ["retire"],
            ["audit", "audit"], ["focus:1", "focus:2", "checkpoint"],
        ):
            with self.subTest(actions=actions):
                with self.assertRaises(AdvancedRuntimeError):
                    run_advanced_session("economy", actions=actions)

    def test_source_rejects_teleport_capital_and_goods_injection(self):
        source = make_advanced_scene("economy")
        for mutate in (
            lambda a: a["layout"]["markets"][1]["site"].__setitem__(0, 17),
            lambda a: a["layout"]["markets"][1].__setitem__("treasury", 99999),
            lambda a: a["layout"]["markets"][1]["inventory"].append(99),
            lambda a: a["layout"].__setitem__("script", "run me"),
            lambda a: a["layout"]["markets"][0].__setitem__("id", 1),
        ):
            modified = copy.deepcopy(source)
            mutate(modified)
            with self.subTest(layout=modified["layout"]):
                with self.assertRaises(SceneError):
                    # This catches altered digest AND semantic invalid layouts.
                    validate_advanced_scene(modified)

    def test_source_rejects_semantically_invalid_rehashed_scene(self):
        source = make_advanced_scene("economy")
        bad = copy.deepcopy(source["layout"])
        bad["markets"][0]["household_cash"] = -1
        with self.assertRaises(SceneError):
            make_advanced_scene("economy", layout=bad)

    def test_receipt_forgery_does_not_create_cash_or_outcome(self):
        original = run_advanced_session("economy", actions=ROUTE)
        for change in (
            lambda a: a["state"].__setitem__("cash", 1000000),
            lambda a: a["state"].__setitem__("checkpoint", False),
            lambda a: a["trace"][-1].__setitem__("events", ["forged_award"]),
            lambda a: a["actions"].__setitem__(0, "retire"),
            lambda a: a.__setitem__("digest", "0" * 64),
        ):
            forged = copy.deepcopy(original)
            change(forged)
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(forged)

    def test_knobs_fail_closed_and_cohorts_are_not_falsely_simulated(self):
        for settings in (
            {"finite_inventory": False}, {"goods": 2},
            {"market_nodes": 1}, {"price_floor": 12, "base_price": 8},
            {"market_treasury": 0}, {"starting_cash": 0},
            {"starting_stock": 64, "warehouse_capacity": 16},
        ):
            with self.subTest(settings=settings):
                with self.assertRaises(SystemEditorError):
                    make_editor_document("economy", settings)
        config = {"goods": 500, "market_nodes": 100}
        scene = make_advanced_scene("economy", config, seed=77)
        state = run_advanced_session("economy", config, seed=77,
                                     scene=scene)["state"]
        self.assertEqual(state["active_market_count"], 8)
        self.assertEqual(len(state["active_goods"]), 8)
        self.assertEqual(state["unmodeled_good_families"], 492)
        self.assertEqual(state["unmodeled_market_nodes"], 92)

    def test_small_budget_supported_without_spurious_phantom_markets(self):
        config = {"goods": 3, "market_nodes": 2, "active_market_budget": 2}
        scene = make_advanced_scene("economy", config, seed=10)
        result = run_advanced_session("economy", config, ROUTE, seed=10,
                                      scene=scene)
        self.assertTrue(result["state"]["checkpoint"])
        self.assertEqual(len(result["state"]["markets"]), 2)
        self.assertTrue(verify_advanced_session(result, config))


if __name__ == "__main__":
    unittest.main()
