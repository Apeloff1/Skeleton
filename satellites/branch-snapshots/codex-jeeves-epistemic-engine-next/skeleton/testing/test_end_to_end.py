"""
Skeleton — End-to-end system test

This test exercises the complete platform from genesis boot through
all subsystems, verifying integration points and event flow.
"""

from __future__ import annotations

import unittest
from skeleton.testing.scaffold import TestCase


class TestGenesisBootSequence(TestCase):
    """Verify all 7 genesis phases boot correctly."""

    def test_kernel_phase(self):
        """Kernel provides EventBus, EntropyPool, VectorClock, InvariantLattice."""
        self.assertHandleWired("lattice")
        self.assertHandleWired("entropy")
        self.assertHandleWired("clock")
        
        lattice = self.scaffold.get("lattice")
        violations = lattice.evaluate()
        self.assertIsInstance(violations, list)

    def test_memory_phase(self):
        """Memory provides RAG, CAG, MAG, Trinity, Dream, Drift."""
        self.assertHandleWired("rag")
        self.assertHandleWired("cag")
        self.assertHandleWired("mag")
        self.assertHandleWired("trinity")
        self.assertHandleWired("repetition")
        self.assertHandleWired("dream")
        self.assertHandleWired("drift")

    def test_intelligence_phase(self):
        """Intelligence provides Orchestrator and AdaptiveLearner."""
        self.assertHandleWired("orchestrator")
        self.assertHandleWired("adaptive")

    def test_swarm_phase(self):
        """Swarm provides Mesh, Pheromones, Stigmergy, Hive, Negotiator, Platoons."""
        self.assertHandleWired("mesh")
        self.assertHandleWired("pheromones")
        self.assertHandleWired("stigmergy")
        self.assertHandleWired("hive")
        self.assertHandleWired("negotiator")
        self.assertHandleWired("platoons")

    def test_resilience_phase(self):
        """Resilience provides Fortress and Canaries."""
        self.assertHandleWired("fortress")
        self.assertHandleWired("canaries")

    def test_interface_phase(self):
        """Interface provides Anomaly, Provenance, Reranker, Quad."""
        self.assertHandleWired("anomaly")
        self.assertHandleWired("provenance")
        self.assertHandleWired("reranker")
        self.assertHandleWired("quad")

    def test_cortex_phase(self):
        """Cortex provides JeevesCortex observability hub."""
        self.assertHandleWired("cortex")


class TestEventBusIntegration(TestCase):
    """Verify event bus connects all subsystems."""

    def test_cross_subsystem_events(self):
        """Subsystems can communicate via events."""
        bus = self.scaffold.genesis.bus
        events_received = []
        
        def handler(event):
            events_received.append(event.topic)
        
        bus.subscribe("test.integration", handler)
        bus.emit("test.integration", {"data": "cross-subsystem"})
        
        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0], "test.integration")

    def test_genesis_publishes_boot_event(self):
        """Genesis publishes boot completion event."""
        cortex = self.scaffold.get("cortex")
        events = cortex.recent_events("kernel.genesis.booted", n=1)
        self.assertGreaterEqual(len(events), 1)


class TestMemoryTrinity(TestCase):
    """Verify memory planes work together."""

    def test_trinity_query(self):
        """Trinity can query across RAG, CAG, MAG."""
        trinity = self.scaffold.get("trinity")
        result = trinity.query_unified("test query", top_k_per_tier=2)
        self.assertIsNotNone(result)
        self.assertIsInstance(result.combined_score, float)

    def test_rag_add_and_query(self):
        """RAG can store and retrieve documents."""
        rag = self.scaffold.get("rag")
        from skeleton.memory.core import Chunk
        
        chunk = Chunk(text="skeleton platform test document", chunk_id="test-1")
        rag.add(chunk)
        
        results = rag.query("skeleton platform", top_k=3)
        self.assertIsInstance(results, list)


class TestSwarmCoordination(TestCase):
    """Verify swarm can coordinate agents."""

    def test_agent_join_and_route(self):
        """Agents can join the swarm and receive tasks."""
        mesh = self.scaffold.get("mesh")
        agent = mesh.join({"compute", "storage"}, weight=2.0)
        self.assertIsNotNone(agent.agent_id)
        
        routed = mesh.route("compute")
        self.assertIsNotNone(routed)

    def test_hive_mind_consensus(self):
        """HiveMind can reach consensus on scalar values."""
        hive = self.scaffold.get("hive")
        hive.contribute("temperature", "agent-1", 22.5, confidence=0.8)
        hive.contribute("temperature", "agent-2", 23.0, confidence=0.9)
        
        consensus = hive.consensus("temperature")
        self.assertIsNotNone(consensus)
        self.assertIsInstance(consensus, float)


class TestResilienceSecurity(TestCase):
    """Verify resilience subsystem protects against threats."""

    def test_fortress_allows_safe_input(self):
        """Fortress allows normal input."""
        fortress = self.scaffold.get("fortress")
        clean, report = fortress.process_input("Hello, Skeleton platform!")
        self.assertEqual(report.level.value, "none")
        self.assertEqual(report.action_taken, "allowed")

    def test_fortress_blocks_malicious_input(self):
        """Fortress detects and blocks SQL injection patterns."""
        fortress = self.scaffold.get("fortress")
        clean, report = fortress.process_input("'; DROP TABLE users; --")
        self.assertIn(report.action_taken, ["blocked", "sanitized"])


class TestForgeBlueprint(TestCase):
    """Verify forge can create and materialize blueprints."""

    def test_blueprint_validation(self):
        """Blueprints validate component connections."""
        forge = self.scaffold.get("forge")
        bp = forge.new_blueprint("test-validation")
        
        forge.instantiate(bp, "source", "input")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("input", "out"), ("output", "in"))
        
        problems = bp.validate()
        self.assertEqual(len(problems), 0)

    def test_blueprint_detects_cycles(self):
        """Validation catches dependency cycles."""
        forge = self.scaffold.get("forge")
        bp = forge.new_blueprint("test-cycle")
        
        forge.instantiate(bp, "transform", "a")
        forge.instantiate(bp, "transform", "b")
        bp.connect(("a", "out"), ("b", "in"))
        bp.connect(("b", "out"), ("a", "in"))
        
        problems = bp.validate()
        self.assertTrue(any("cycle" in p.lower() for p in problems))


class TestObservability(TestCase):
    """Verify observability captures system state."""

    def test_anomaly_detection(self):
        """Anomaly detector identifies outliers."""
        anomaly = self.scaffold.get("anomaly")
        
        # Feed normal values
        for i in range(20):
            anomaly.observe(10.0 + i * 0.1)
        
        # Anomalous value
        report = anomaly.observe(100.0, metric_name="test.metric")
        self.assertIsNotNone(report)
        self.assertIn(report.severity, ["medium", "high", "critical"])

    def test_cortex_captures_events(self):
        """Cortex captures and queries events."""
        cortex = self.scaffold.get("cortex")
        
        # Emit a test event
        self.scaffold.genesis.bus.emit("test.observability", {"data": "test"})
        
        events = cortex.recent_events("test.observability", n=5)
        self.assertGreaterEqual(len(events), 1)


class TestDeveloperCLI(TestCase):
    """Verify developer CLI is functional."""

    def test_scaffold_templates_exist(self):
        """Scaffold engine has templates."""
        from skeleton.developer.scaffold import list_templates
        templates = list_templates()
        self.assertGreater(len(templates), 0)

    def test_wizard_runs(self):
        """Wizard generates project plans."""
        from skeleton.developer.wizard import Wizard, WizardMode
        wizard = Wizard(mode=WizardMode.QUICK)
        result = wizard.run()
        self.assertIn("Project:", result)


class TestConfigurationSystem(TestCase):
    """Verify layered configuration works."""

    def test_config_has_defaults(self):
        """Configuration loads built-in defaults."""
        from skeleton.config.system import get_config
        cfg = get_config()
        
        # Should have default values
        val = cfg.get("kernel.entropy_seed")
        self.assertIsNone(val)  # Default is None
        
        val = cfg.get("memory.rag.top_k", default=5)
        self.assertEqual(val, 5)


class TestVaultSecurity(TestCase):
    """Verify vault encryption and access control."""

    def test_envelope_encryption(self):
        """KMS can encrypt and decrypt data."""
        from skeleton.vault.access import EnvelopeKMS
        
        kms = EnvelopeKMS()
        plaintext = b"skeleton secret data"
        
        envelope = kms.encrypt(plaintext, context="test")
        decrypted = kms.decrypt(envelope)
        
        self.assertEqual(decrypted, plaintext)

    def test_role_permissions(self):
        """Roles enforce permission boundaries."""
        from skeleton.vault.access import Permission, ROLE_ADMIN, ROLE_GUEST, AccessPolicy
        
        policy = AccessPolicy(resource="test-resource")
        policy.grant("admin", ROLE_ADMIN)
        policy.grant("guest", ROLE_GUEST)
        
        self.assertTrue(policy.check("admin", Permission.WRITE))
        self.assertFalse(policy.check("guest", Permission.WRITE))


class TestGalaxyFederation(TestCase):
    """Verify distributed galaxy node coordination."""

    def test_node_registration(self):
        """Nodes can register and discover each other."""
        from skeleton.galaxy.federation import NodeRegistry
        
        registry = NodeRegistry()
        node = registry.register("node-1", "192.168.1.1", region="us-east", capabilities={"compute", "storage"})
        
        self.assertEqual(node.node_id, "node-1")
        discovered = registry.discover(capability="compute")
        self.assertEqual(len(discovered), 1)

    def test_consensus_proposal(self):
        """Galaxy can form consensus across nodes."""
        from skeleton.galaxy.federation import FederationMesh, NodeRegistry
        
        registry = NodeRegistry()
        mesh = FederationMesh(registry)
        
        registry.register("node-1", "192.168.1.1")
        registry.register("node-2", "192.168.1.2")
        
        proposal_id = mesh.propose("config.update", {"setting": "value"})
        self.assertIsNotNone(proposal_id)


class TestSocialGraph(TestCase):
    """Verify social interaction tracking."""

    def test_reputation_computation(self):
        """Reputation engine computes agent trust scores."""
        from skeleton.social.graph import SocialGraph, ReputationEngine
        
        graph = SocialGraph()
        rep = ReputationEngine(graph)
        
        graph.record_interaction("agent-a", "agent-b", "cooperate", 1.0)
        graph.record_interaction("agent-b", "agent-a", "cooperate", 0.8)
        
        score = rep.compute_reputation("agent-a", method="simple")
        self.assertGreater(score, 0)


class TestAssetManagement(TestCase):
    """Verify acquired asset ingestion."""

    def test_asset_library_catalogs(self):
        """Asset library can catalog and retrieve assets."""
        from skeleton.acquired.ingest import AssetLibrary
        
        library = AssetLibrary()
        
        # Create a temporary file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            temp_path = f.name
        
        result = library.ingest(temp_path, "test-asset", "image", tags=["test"])
        self.assertTrue(result["valid"])
        self.assertIn("asset_id", result)
        
        # Cleanup
        import os
        os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
