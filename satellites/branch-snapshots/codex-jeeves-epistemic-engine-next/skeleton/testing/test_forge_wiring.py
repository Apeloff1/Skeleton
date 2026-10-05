"""Tests for genesis forge wiring."""

from __future__ import annotations

import unittest


class TestGenesisForgeWiring(unittest.TestCase):
    def setUp(self):
        from skeleton.genesis import Genesis
        self.genesis = Genesis(seed=42).boot()

    def test_forge_handle_wired(self):
        forge = self.genesis.handles.get("forge")
        self.assertIsNotNone(forge, "forge handle not wired in genesis")

    def test_forge_in_phases(self):
        self.assertIn("forge", self.genesis.report.phases)

    def test_forge_uses_genesis_bus(self):
        forge = self.genesis.get("forge")
        received = []
        self.genesis.bus.subscribe("forge.blueprint.created", lambda e: received.append(e))
        forge.new_blueprint("bus-check")
        self.assertEqual(len(received), 1)

    def test_forge_stdlib_kinds(self):
        forge = self.genesis.get("forge")
        kinds = forge.available_kinds()
        for kind in ("source", "transform", "sink", "player", "heat", "weapon_forge", "enemy_spawner", "collapse", "extract", "jeeves"):
            self.assertIn(kind, kinds)

    def test_forge_invariant_registered(self):
        violations = self.genesis.lattice.evaluate()
        self.assertNotIn("forge_kinds_registered", violations)

    def test_materialize_through_genesis_forge(self):
        forge = self.genesis.get("forge")
        bp = forge.new_blueprint("genesis-materialise")
        forge.instantiate(bp, "source", "input")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("input", "out"), ("output", "in"))
        result = forge.materialise(bp, era="extraction_now", target="json")
        self.assertEqual(result["blueprint_id"], bp.blueprint_id)

    def test_harness_materialize_works(self):
        from skeleton.deploy.harness import Harness
        harness = Harness(seed=42)
        harness.boot()
        result = harness.materialize("harness-bp")
        self.assertIn("blueprint_id", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
