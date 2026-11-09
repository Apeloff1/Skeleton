from __future__ import annotations

from types import SimpleNamespace

from skeleton.api.server import ServerState


class _Runtime:
    def __init__(self) -> None:
        self.dispatched = 0
        self.started = 0
        self.closed = 0
        self._closed = False

    def dispatch_outbox(self):
        self.dispatched += 1
        return SimpleNamespace(healthy=True)

    def start_dispatcher(self):
        self.started += 1
        return self.started == 1

    def close(self):
        self.closed += 1
        self._closed = True


class _Factory:
    runtime = _Runtime()
    calls = 0

    @classmethod
    def from_settings(cls, orchestrator, settings):
        cls.calls += 1
        cls.runtime = _Runtime()
        cls.runtime.orchestrator = orchestrator
        cls.runtime.settings = settings
        return cls.runtime


def test_server_state_binds_and_starts_durable_operation_runtime(monkeypatch) -> None:
    state = ServerState()
    core = object()
    state.intelligence_core = core

    monkeypatch.setattr(
        "skeleton.persistence.operation_runtime.DurableOperationRuntime",
        _Factory,
    )
    settings = SimpleNamespace(operation=SimpleNamespace())
    monkeypatch.setattr(
        "skeleton.config.settings.get_settings",
        lambda: settings,
    )

    runtime = state.bind_operation_runtime()

    assert runtime is _Factory.runtime
    assert runtime.orchestrator is core
    assert runtime.settings is settings.operation
    assert runtime.dispatched == 1
    assert runtime.started == 1
    assert state.operation_runtime is runtime
    assert state.intelligence is runtime


def test_server_state_operation_runtime_binding_is_idempotent(monkeypatch) -> None:
    state = ServerState()
    state.intelligence_core = object()

    monkeypatch.setattr(
        "skeleton.persistence.operation_runtime.DurableOperationRuntime",
        _Factory,
    )
    monkeypatch.setattr(
        "skeleton.config.settings.get_settings",
        lambda: SimpleNamespace(operation=SimpleNamespace()),
    )

    first = state.bind_operation_runtime()
    second = state.bind_operation_runtime()

    assert second is first
    assert _Factory.calls >= 1
    assert first.started == 1


def test_server_state_shutdown_closes_dispatcher_runtime() -> None:
    state = ServerState()
    runtime = _Runtime()
    state.operation_runtime = runtime
    state.intelligence_core = object()
    state.intelligence = runtime

    state.close_operation_runtime()

    assert runtime.closed == 1
    assert state.operation_runtime is None
    assert state.intelligence is state.intelligence_core
