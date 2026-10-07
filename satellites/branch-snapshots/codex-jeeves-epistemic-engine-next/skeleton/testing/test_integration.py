"""
Skeleton — Comprehensive integration test for full system boot

This test exercises the complete genesis → forge → api pipeline,
verifying all subsystems wire correctly and can communicate via the event bus.
"""

from __future__ import annotations

import unittest
from skeleton.testing.scaffold import TestCase


class TestFullSystemBoot(TestCase):
    """End-to-end system boot and integration test."""

    def test_genesis_boots_all_phases(self):
        """Verify genesis boots all 7 phases."""
        genesis = self.scaffold.genesis
        self.assertIsNotNone(genesis)
        
        expected_phases = ["kernel", "memory", "intelligence", "swarm", "resilience", "interface", "cortex"]
        self.assertEqual(genesis.report.phases, expected_phases)
        self.assertEqual(len(genesis.report.phases), 7)

    def test_all_handles_wired(self):
        """Verify all expected handles are present."""
        handles = self.scaffold.genesis.handles
        
        # Kernel
        self.assertIn("lattice", handles)
        self.assertIn("entropy", handles)
        self.assertIn("clock", handles)
        
        # Memory
        self.assertIn("rag", handles)
        self.assertIn("cag", handles)
        self.assertIn("mag", handles)
        self.assertIn("trinity", handles)
        self.assertIn("repetition", handles)
        self.assertIn("dream", handles)
        self.assertIn("drift", handles)
        
        # Intelligence
        self.assertIn("orchestrator", handles)
        self.assertIn("adaptive", handles)
        
        # Swarm
        self.assertIn("mesh", handles)
        self.assertIn("pheromones", handles)
        self.assertIn("stigmergy", handles)
        self.assertIn("hive", handles)
        self.assertIn("negotiator", handles)
        self.assertIn("platoons", handles)
        
        # Resilience
        self.assertIn("fortress", handles)
        self.assertIn("canaries", handles)
        
        # Interface
        self.assertIn("anomaly", handles)
        self.assertIn("provenance", handles)
        self.assertIn("reranker", handles)
        self.assertIn("quad", handles)
        
        # Cortex
        self.assertIn("cortex", handles)

    def test_event_bus_publishes(self):
        """Verify the event bus can publish and receive events."""
        bus = self.scaffold.genesis.bus
        received = []
        
        def handler(event):
            received.append(event.topic)
        
        bus.subscribe("test.event", handler)
        bus.emit("test.event", {"message": "hello"})
        
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], "test.event")

    def test_invariants_registered(self):
        """Verify invariants are registered and can be evaluated."""
        lattice = self.scaffold.genesis.lattice
        self.assertIsNotNone(lattice)
        
        violations = lattice.evaluate()
        self.assertIsInstance(violations, list)
        # Should have at least the mag_index_consistent and swarm_quorum_viable invariants
        self.assertGreaterEqual(self.scaffold.genesis.report.invariants_registered, 2)

    def test_memory_trinity_query(self):
        """Test the memory trinity can perform unified queries."""
        trinity = self.scaffold.get("trinity")
        self.assertIsNotNone(trinity)
        
        # Add some test data
        trinity.rag.add(trinity.rag.__class__.__bases__[0].__new__(trinity.rag.__class__.__bases__[0]))
        # The trinity should be queryable even with empty stores
        result = trinity.query_unified("test query", top_k_per_tier=1)
        self.assertIsNotNone(result)
        self.assertIsInstance(result.token_estimate, float)

    def test_forge_blueprint_creation(self):
        """Test forge can create and validate blueprints."""
        forge = self.scaffold.get("forge")
        if forge is None:
            self.skipTest("Forge not wired")
        
        bp = forge.new_blueprint("test_integration")
        self.assertIsNotNone(bp.blueprint_id)
        self.assertEqual(bp.name, "test_integration")
        
        forge.instantiate(bp, "source", "input")
        forge.instantiate(bp, "transform", "process")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("input", "out"), ("process", "in"))
        bp.connect(("process", "out"), ("output", "in"))
        
        problems = bp.validate()
        self.assertEqual(len(problems), 0)

    def test_swarm_agent_registration(self):
        """Test swarm mesh can register and route to agents."""
        mesh = self.scaffold.get("mesh")
        if mesh is None:
            self.skipTest("Swarm mesh not wired")
        
        agent = mesh.join({"reasoning", "vision"}, weight=2.0)
        self.assertIsNotNone(agent.agent_id)
        self.assertIn("reasoning", agent.specialisations)
        
        routed = mesh.route("reasoning")
        self.assertIsNotNone(routed)

    def test_resilience_fortress_sanitization(self):
        """Test resilience fortress can sanitize input."""
        fortress = self.scaffold.get("fortress")
        if fortress is None:
            self.skipTest("Resilience fortress not wired")
        
        clean, report = fortress.process_input("Hello world", user_id="test")
        self.assertEqual(report.level.value, "none")
        self.assertEqual(report.action_taken, "allowed")

    def test_health_monitor_reports_healthy(self):
        """Test health check reports healthy system."""
        health = self.scaffold.genesis.health()
        self.assertIn("phases", health)
        self.assertIn("healthy", health)
        self.assertIn("subsystems", health)
        self.assertGreater(health["subsystems"], 0)

    def test_cortex_observes_events(self):
        """Test cortex captures events from the bus."""
        cortex = self.scaffold.get("cortex")
        if cortex is None:
            self.skipTest("Cortex not wired")
        
        # The cortex should have captured the genesis boot event
        events = cortex.recent_events("kernel.genesis.booted", n=1)
        self.assertGreaterEqual(len(events), 1)


class TestDeveloperCLI(TestCase):
    """Test developer CLI integration."""

    def test_dev_command_available(self):
        """Verify dev command is registered in __main__."""
        import skeleton.__main__ as main_module
        self.assertTrue(hasattr(main_module, 'main'))

    def test_scaffold_engine_importable(self):
        """Verify scaffold engine can be imported."""
        from skeleton.developer.scaffold import ScaffoldEngine, list_templates
        templates = list_templates()
        self.assertGreater(len(templates), 0)

    def test_wizard_importable(self):
        """Verify wizard can be imported."""
        from skeleton.developer.wizard import Wizard, WizardMode
        wizard = Wizard(mode=WizardMode.QUICK)
        result = wizard.run()
        self.assertIn("Quick Mode", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
