"""Original economy execution, conservation, and source replay."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_economy_runtime import EconomyActionError
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene,
)


class MarketEngineTests(unittest.TestCase):
    def test_trades_move_inventory_and_credits_with_tax(self):
        game = run_advanced_session("economy", {"market_nodes": 2, "goods": 10,
                                                 "trade_tax": 10},
                                    ["buy:1", "travel:1", "sell:1"], seed=1)
        self.assertTrue(verify_advanced_session(game, {"market_nodes": 2,
                      "goods": 10, "trade_tax": 10}))
        self.assertEqual(game["state"]["trade_volume"], 2)
        self.assertEqual(game["state"]["cargo"], 0)
        self.assertGreater(game["state"]["tax_collected"], 0)
        self.assertEqual(game["state"]["journeys"], 1)
        self.assertEqual(len(game["state"]["journal"]), 3)
        self.assertTrue(any("physical_goods_sold_to_funded_market" in t["events"]
                            for t in game["trace"]))

    def test_source_bound_adversarial_ledger_and_finite_stock(self):
        source = make_advanced_scene("economy", {"goods": 4, "market_nodes": 1})
        session = run_advanced_session("economy", {"goods": 4, "market_nodes": 1},
                                       ["inspect"], scene=source)
        self.assertTrue(verify_advanced_session(session, {"goods": 4,
                         "market_nodes": 1}))
        forged = deepcopy(session)
        forged["state"]["credits"] += 100
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged, {"goods": 4, "market_nodes": 1})
        source["layout"]["nodes"][0]["stock"] = 999
        with self.assertRaises(SceneError):
            run_advanced_session("economy", {"goods": 4, "market_nodes": 1}, scene=source)

    def test_rejection_of_unfunded_orders_and_fake_milestones(self):
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("economy", actions=["sell:1"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("economy", actions=["checkpoint"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("economy", actions=["travel:99"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("economy", actions=["borrow"] * 9)
        with self.assertRaises(EconomyActionError):
            raise EconomyActionError("invalid economy")


if __name__ == "__main__":
    unittest.main()
