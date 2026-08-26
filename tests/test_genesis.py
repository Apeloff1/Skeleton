"""Deep tests for the Genesis boot protocol."""

from skeleton.genesis import Genesis


class TestGenesisBoot:
    def test_all_phases_run(self):
        g = Genesis(seed=7).boot()
        assert g.report.phases == [
            "kernel", "memory", "intelligence", "swarm", "resilience", "interface",
        ]

    def test_shared_bus(self):
        g = Genesis(seed=7).boot()
        assert g.bus.published_count >= 1
        topics = [e.topic for e in g.bus.replay("*")]
        assert "kernel.genesis.booted" in topics

    def test_handles_present(self):
        g = Genesis(seed=7).boot()
        required = {
            "lattice", "entropy", "clock",
            "rag", "cag", "mag", "trinity", "repetition", "dream", "drift",
            "orchestrator", "adaptive",
            "mesh", "pheromones", "stigmergy", "hive", "negotiator", "platoons",
            "fortress", "canaries",
            "anomaly", "provenance", "reranker",
        }
        assert required <= set(g.handles)

    def test_health_shape(self):
        g = Genesis(seed=7).boot()
        h = g.health()
        assert h["subsystems"] >= 20
        assert "bus" in h
        assert h["invariant_violations"] == 0
        assert h["healthy"] is True

    def test_deterministic_wiring(self):
        a = Genesis(seed=42).boot()
        b = Genesis(seed=42).boot()
        assert a.report.to_dict()["wired"] == b.report.to_dict()["wired"]

    def test_get(self):
        g = Genesis(seed=1).boot()
        assert g.get("trinity") is g.handles["trinity"]
