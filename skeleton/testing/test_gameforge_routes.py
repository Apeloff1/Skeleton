"""Tests for GameForge API routes (handler-level, without running a server)."""

from __future__ import annotations

import unittest


class TestGameForgeRouteLogic(unittest.TestCase):
    def test_intake_logic(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis
        from skeleton.pipelines import GameForge

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())

        forge = GameForge(genesis=state.genesis, bus=state.genesis.bus)
        result = forge.intake({"genre": "strategy", "theme": "cyberpunk"})
        # Brief votes a canonical, compilable era; the setting label is separate.
        self.assertEqual(result["era"], "grand_strategy")
        self.assertEqual(result["setting"], "neon_dystopia")
        self.assertIn("strategy", result["vision"])

    def test_run_logic_matches_api_shape(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis
        from skeleton.pipelines import GameForge

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())

        forge = GameForge(genesis=state.genesis, bus=state.genesis.bus)
        spec = forge.run({"genre": "rpg", "theme": "fantasy"}, title="Testlands")
        response = {"game": spec.to_dict(), "status": "generated"}

        self.assertEqual(response["status"], "generated")
        self.assertEqual(response["game"]["title"], "Testlands")
        self.assertEqual(response["game"]["era"], "crpg")
        self.assertTrue(response["game"]["blueprint_id"].startswith("bp-"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
