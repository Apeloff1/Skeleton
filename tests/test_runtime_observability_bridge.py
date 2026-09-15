"""Regression coverage for the canonical runtime observability attachment."""

from __future__ import annotations

from skeleton.agents.coordination import TaskStatus
from skeleton.foundation.journal import EventJournal, JournaledBus
from skeleton.genesis import Genesis
from skeleton.kernel.events import EventBus
from skeleton.observability.orchestration import ObservableOrchestrator


def test_journaled_bus_preserves_correlation_and_emits_baseline_metrics() -> None:
    raw_bus = EventBus()
    journal = EventJournal()
    bus = JournaledBus(raw_bus, journal)

    bus.emit(
        "orchestration.tool.failed",
        {
            "request_id": "req-121",
            "status": "failed",
            "duration_ms": 12.5,
        },
    )

    entry = journal.entry(0)
    assert entry is not None
    assert entry.correlation_id == "req-121"

    observed = bus.metrics_bridge.events()
    assert len(observed) == 1
    assert observed[0].correlation_id == "req-121"
    assert observed[0].topic == "orchestration.tool.failed"

    registry = bus.metrics_bridge.registry
    labels = {"topic": "orchestration.tool.failed"}
    assert registry.get_counter("observability.events_total", labels=labels) == 1.0
    assert registry.get_counter("observability.failures_total", labels=labels) == 1.0
    assert registry.histogram_stats("observability.latency_ms", labels=labels)["count"] == 1


def test_journaled_bus_explicit_correlation_wins_over_payload_inference() -> None:
    journal = EventJournal()
    bus = JournaledBus(EventBus(), journal)

    bus.emit(
        "orchestration.run.succeeded",
        {"run_id": "run-payload", "status": "succeeded"},
        correlation_id="request-explicit",
    )

    entry = journal.entry(0)
    assert entry is not None
    assert entry.correlation_id == "request-explicit"
    assert bus.metrics_bridge.events()[-1].correlation_id == "request-explicit"


def test_genesis_runtime_attaches_shared_event_metrics_bridge() -> None:
    genesis = Genesis(seed=42).boot()

    assert isinstance(genesis.bus, JournaledBus)
    bridge = genesis.bus.metrics_bridge
    before = len(bridge.events())

    genesis.bus.emit(
        "runtime.capacity.sample",
        {
            "run_id": "run-121",
            "queue_depth": 7,
            "memory_bytes": 4096,
        },
    )

    assert len(bridge.events()) == before + 1
    event = bridge.events()[-1]
    assert event.correlation_id == "run-121"
    assert event.topic == "runtime.capacity.sample"
    assert bridge.registry.get_gauge("observability.queue_depth") == 7.0
    assert bridge.registry.get_gauge("observability.memory_bytes") == 4096.0


def test_observable_orchestrator_reuses_genesis_runtime_bridge() -> None:
    genesis = Genesis(seed=42).boot()

    assert isinstance(genesis.bus, JournaledBus)
    bridge = genesis.bus.metrics_bridge
    subscriptions_before = genesis.bus.stats()["bus"]["subscribed"]

    orchestrator = ObservableOrchestrator(event_bus=genesis.bus)

    assert orchestrator.metrics_bridge is bridge
    assert genesis.bus.stats()["bus"]["subscribed"] == subscriptions_before


def test_genesis_agent_handler_keeps_request_correlation_through_tool_run() -> None:
    genesis = Genesis(seed=42).boot()

    assert isinstance(genesis.bus, JournaledBus)
    bridge = genesis.bus.metrics_bridge
    coordinator = genesis.handles["coordinator"]
    coordinator.register_handler("work", lambda task: f"done:{task.description}")
    before = len(bridge.events())

    task = coordinator.dispatch(
        "correlated job",
        task_type="work",
        metadata={"request_id": "req-agent-121"},
    )

    assert task.status is TaskStatus.COMPLETED
    events = bridge.events()[before:]
    correlated_topics = {
        event.topic
        for event in events
        if event.correlation_id == "req-agent-121"
    }
    assert {
        "agents.task.assigned",
        "orchestration.run.started",
        "orchestration.tool.started",
        "orchestration.tool.succeeded",
        "orchestration.run.completed",
        "agents.coordinator.dispatched",
    } <= correlated_topics
