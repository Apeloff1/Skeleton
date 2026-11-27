"""Tests for hardening modules: ranking, dream engine, kms, sampling, kernel re-exports."""

from __future__ import annotations

import time
import unittest


class TestRanking(unittest.TestCase):
    def test_ranker_blends_scores(self):
        from skeleton.retrieval.ranking import Ranker
        from skeleton.retrieval.fusion import ScoredResult

        ranker = Ranker()
        results = [
            ScoredResult(fragment_id="a", content="alpha content", score=0.5),
            ScoredResult(fragment_id="b", content="beta content", score=0.8),
        ]
        ranked = ranker.rank(results)
        self.assertEqual(ranked[0].fragment_id, "b")
        self.assertGreater(ranker.stats()["ranked"], 0)

    def test_ranker_diversity_penalty(self):
        from skeleton.retrieval.ranking import Ranker
        from skeleton.retrieval.fusion import ScoredResult

        ranker = Ranker(diversity_weight=0.5)
        dup = "identical content here"
        results = [
            ScoredResult(fragment_id="a", content=dup, score=0.9),
            ScoredResult(fragment_id="b", content=dup, score=0.9),
            ScoredResult(fragment_id="c", content="unique", score=0.8),
        ]
        ranked = ranker.rank(results)
        self.assertEqual(ranked[0].fragment_id, "a")  # first occurrence keeps full boost


class TestDreamEngine(unittest.TestCase):
    def test_dream_synthesizes_themes(self):
        from skeleton.intelligence.dream import DreamEngine
        from skeleton.memory.core import InMemoryTFIDFStore, MAGStore

        rag = InMemoryTFIDFStore()
        mag = MAGStore("agent-1")
        mag.record("e1", "defended the gate", tags=["combat"])
        mag.record("e2", "fought raiders", tags=["combat"])

        dream = DreamEngine(mag, rag)
        themes = dream.dream(min_cluster=2)
        self.assertEqual(len(themes), 1)
        self.assertEqual(themes[0]["tag"], "combat")
        self.assertEqual(dream.stats()["themes"], 1)

    def test_dream_skips_small_clusters(self):
        from skeleton.intelligence.dream import DreamEngine
        from skeleton.memory.core import InMemoryTFIDFStore, MAGStore

        mag = MAGStore("agent-1")
        mag.record("e1", "single event", tags=["solo"])
        dream = DreamEngine(mag, InMemoryTFIDFStore())
        self.assertEqual(dream.dream(min_cluster=2), [])


class TestKernelReexports(unittest.TestCase):
    def test_canonical_import_paths(self):
        from skeleton.kernel.errors import SkeletonError, BlueprintError, MaterialisationError
        from skeleton.kernel.events import DomainEvent, EventBus
        from skeleton.kernel.registry import CapabilityRegistry
        from skeleton.kernel.entropy import EntropyPool
        from skeleton.kernel.clocks import VectorClock
        from skeleton.kernel.invariants import Invariant, InvariantLattice
        from skeleton.kernel.ids import UserId, BlueprintId

        self.assertTrue(issubclass(BlueprintError, SkeletonError))
        bus = EventBus()
        bus.emit("test", {})
        self.assertEqual(bus.stats()["published"], 1)
        self.assertTrue(UserId.new())
        self.assertTrue(BlueprintId.new().startswith("bp-"))

    def test_registry_reexport_preserves_canonical_metadata_and_listing(self):
        from skeleton.kernel.primitives import CapabilityRegistry as PrimitiveRegistry
        from skeleton.kernel.registry import CapabilityKind, CapabilityRegistry

        self.assertIs(CapabilityRegistry, PrimitiveRegistry)
        registry = CapabilityRegistry()
        metadata = {"kind": CapabilityKind.READ, "scope": "game-project"}
        registry.register("project.inspect", metadata=metadata)
        registry.register("project.create")

        self.assertEqual(
            [capability.to_dict() for capability in registry.list()],
            [{"name": "project.inspect"}, {"name": "project.create"}],
        )
        self.assertIs(registry._capabilities["project.inspect"], metadata)
        self.assertEqual(registry._capabilities["project.create"], {})

    def test_registry_bootstrap_uses_canonical_registry_with_independent_state(self):
        from skeleton.kernel.primitives import CapabilityRegistry
        from skeleton.kernel.registry import CapabilityKind, bootstrap_registry

        first = bootstrap_registry()
        second = bootstrap_registry()
        self.assertIs(type(first), CapabilityRegistry)
        self.assertIs(type(second), CapabilityRegistry)
        self.assertEqual((CapabilityKind.READ, CapabilityKind.WRITE, CapabilityKind.EXECUTE),
                         ("read", "write", "execute"))
        first.register("project.write", metadata={"kind": CapabilityKind.WRITE})
        self.assertEqual([capability.name for capability in first.list()], ["project.write"])
        self.assertEqual(second.list(), [])

    def test_root_package_imports_resolve(self):
        import skeleton
        # Every name in __all__ must actually exist
        for name in skeleton.__all__:
            self.assertTrue(hasattr(skeleton, name), f"missing export: {name}")


class TestKMS(unittest.TestCase):
    def test_kms_module_roundtrip(self):
        from skeleton.vault.kms import EnvelopeKMS

        kms = EnvelopeKMS()
        envelope = kms.encrypt(b"secret payload", context="test")
        self.assertEqual(kms.decrypt(envelope), b"secret payload")


class TestSampling(unittest.TestCase):
    def test_default_sampler(self):
        from skeleton.observability.sampling import Sampler, default_sampler

        sampler = default_sampler()
        self.assertIsInstance(sampler, Sampler)
        self.assertEqual(sampler.base_rate, 0.1)

    def test_error_adapts_rate(self):
        from skeleton.observability.sampling import Sampler

        sampler = Sampler(base_rate=0.1)
        sampler.record_error()
        self.assertGreater(sampler.stats()["rate"], 0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
