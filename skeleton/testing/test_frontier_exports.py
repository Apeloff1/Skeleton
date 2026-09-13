from skeleton import frontier


def test_public_frontier_exports_are_resolvable():
    names = {
        "AgentRuntime", "CapabilityPolicy", "LearningState", "LoreIndex",
        "GenerationRequest", "SimulationTick", "TelemetryBuffer",
    }
    assert names.issubset(set(frontier.__all__))
    for name in names:
        assert getattr(frontier, name) is not None
