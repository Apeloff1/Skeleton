from skeleton import frontier


def test_public_frontier_exports_are_resolvable():
    names = {
        "AgentRuntime", "CapabilityPolicy", "LearningState", "LoreIndex",
        "GenerationRequest", "SimulationTick", "TelemetryBuffer",
    }
    assert names.issubset(set(frontier.__all__))
    for name in names:
        assert getattr(frontier, name) is not None
def test_integrated_runtime_exports_are_available():
    from skeleton import frontier

    for name in ("ExecutionPolicy", "ExecutionStatus", "RuntimeBusy", "RuntimeClosed",
                 "TransientAgentError", "SingleFlight", "IdempotencyConflict", "SQLiteMemoryStore"):
        assert name in frontier.__all__
        assert getattr(frontier, name) is not None
