from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.jvm_accelerators import (
    JvmAcceleratorRegistry,
    JvmAcceleratorRegistryError,
)


@dataclass
class _FakeAccelerator:
    name: str
    fail_ping: bool = False
    ping_calls: int = 0
    restart_calls: int = 0
    close_calls: int = 0
    running: bool = False
    closed: bool = False
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    starts: int = 0
    restarts: int = 0

    def ping(self) -> int:
        self.ping_calls += 1
        self.requests += 1
        if self.fail_ping:
            self.failed_requests += 1
            self.running = False
            raise RuntimeError(f"{self.name} unavailable")
        if not self.running:
            self.starts += 1
        self.running = True
        self.closed = False
        self.successful_requests += 1
        return 8

    def restart(self) -> None:
        self.restart_calls += 1
        self.restarts += 1
        self.running = False
        self.ping()

    def close(self) -> None:
        self.close_calls += 1
        self.running = False
        self.closed = True

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(
            running=self.running,
            closed=self.closed,
            java_binary=sys.executable,
            source=f"/tmp/{self.name}.java",
            pid=123 if self.running else None,
            server_processors=8 if self.running else None,
            starts=self.starts,
            restarts=self.restarts,
            requests=self.requests,
            successful_requests=self.successful_requests,
            failed_requests=self.failed_requests,
            timeouts=0,
            last_error=(
                f"{self.name} unavailable"
                if self.fail_ping and self.failed_requests
                else None
            ),
        )


def _registry(
    tmp_path: Path,
    *,
    failing: str | None = None,
) -> tuple[JvmAcceleratorRegistry, dict[str, _FakeAccelerator], dict[str, int]]:
    names = ("observability", "vector", "physics", "retrieval")
    instances = {
        name: _FakeAccelerator(name, fail_ping=name == failing)
        for name in names
    }
    factory_calls = {name: 0 for name in names}
    source_paths: dict[str, Path] = {}
    for name in names:
        source = tmp_path / f"{name}.java"
        source.write_text("// test source\n", encoding="utf-8")
        source_paths[name] = source

    def factory_for(name: str):
        def factory() -> _FakeAccelerator:
            factory_calls[name] += 1
            return instances[name]
        return factory

    def config_for(name: str):
        def provider() -> SimpleNamespace:
            return SimpleNamespace(
                java_binary=sys.executable,
                source=source_paths[name],
            )
        return provider

    registry = JvmAcceleratorRegistry(
        factories={name: factory_for(name) for name in names},
        config_providers={name: config_for(name) for name in names},
    )
    return registry, instances, factory_calls


def test_preflight_and_status_do_not_initialize_helpers(tmp_path: Path) -> None:
    registry, _instances, factory_calls = _registry(tmp_path)

    preflight = registry.preflight()
    status = registry.status()

    assert set(preflight) == {"observability", "vector", "physics", "retrieval"}
    assert all(item.ready for item in preflight.values())
    assert all(not item.initialized for item in status.values())
    assert all(item.healthy for item in status.values())
    assert factory_calls == {
        "observability": 0,
        "vector": 0,
        "physics": 0,
        "retrieval": 0,
    }


def test_get_initializes_only_requested_accelerator(tmp_path: Path) -> None:
    registry, instances, factory_calls = _registry(tmp_path)

    vector = registry.get("vector")

    assert vector is instances["vector"]
    assert registry.initialized("vector") is True
    assert registry.initialized("physics") is False
    assert factory_calls["vector"] == 1
    assert factory_calls["physics"] == 0
    assert registry.get("vector") is vector
    assert factory_calls["vector"] == 1


def test_concurrent_get_constructs_one_accelerator_instance(tmp_path: Path) -> None:
    source = tmp_path / "vector.java"
    source.write_text("// test source\n", encoding="utf-8")
    created: list[_FakeAccelerator] = []
    created_lock = threading.Lock()
    start = threading.Barrier(12)

    def factory() -> _FakeAccelerator:
        with created_lock:
            instance = _FakeAccelerator(f"vector-{len(created)}")
            created.append(instance)
        time.sleep(0.02)
        return instance

    registry = JvmAcceleratorRegistry(
        factories={"vector": factory},
        config_providers={
            "vector": lambda: SimpleNamespace(
                java_binary=sys.executable,
                source=source,
            )
        },
    )

    def get_vector() -> object:
        start.wait()
        return registry.get("vector")

    with ThreadPoolExecutor(max_workers=12) as pool:
        instances = list(pool.map(lambda _index: get_vector(), range(12)))

    assert len(created) == 1
    assert all(instance is created[0] for instance in instances)


def test_close_serializes_against_concurrent_get(tmp_path: Path) -> None:
    source = tmp_path / "vector.java"
    source.write_text("// test source\n", encoding="utf-8")
    close_started = threading.Event()
    close_release = threading.Event()
    created: list[_FakeAccelerator] = []

    class BlockingCloseAccelerator(_FakeAccelerator):
        def close(self) -> None:
            close_started.set()
            assert close_release.wait(timeout=2.0)
            super().close()

    def factory() -> _FakeAccelerator:
        if not created:
            instance: _FakeAccelerator = BlockingCloseAccelerator("vector-first")
        else:
            instance = _FakeAccelerator("vector-next")
        created.append(instance)
        return instance

    registry = JvmAcceleratorRegistry(
        factories={"vector": factory},
        config_providers={
            "vector": lambda: SimpleNamespace(
                java_binary=sys.executable,
                source=source,
            )
        },
    )
    first = registry.get("vector")

    with ThreadPoolExecutor(max_workers=2) as pool:
        closing = pool.submit(registry.close, "vector")
        assert close_started.wait(timeout=1.0)
        getting = pool.submit(registry.get, "vector")
        time.sleep(0.05)
        assert getting.done() is False
        close_release.set()
        closing.result(timeout=2.0)
        second = getting.result(timeout=2.0)

    assert first.closed is True
    assert second is not first
    assert len(created) == 2


def test_health_probe_redacts_exception_text(tmp_path: Path) -> None:
    registry = JvmAcceleratorRegistry(
        config_providers={
            "vector": lambda: (_ for _ in ()).throw(
                RuntimeError("password=hunter2")
            )
        }
    )

    result = registry.health_probe("vector")()

    assert result.ok is False
    assert result.detail == "RuntimeError"
    assert "hunter2" not in result.detail


def test_warm_all_starts_each_helper_and_surfaces_runtime_counters(tmp_path: Path) -> None:
    registry, instances, _factory_calls = _registry(tmp_path)

    statuses = registry.warm()

    assert all(status.running for status in statuses.values())
    assert all(status.initialized for status in statuses.values())
    assert all(status.starts == 1 for status in statuses.values())
    assert all(status.requests == 1 for status in statuses.values())
    assert all(status.successful_requests == 1 for status in statuses.values())
    assert all(status.failed_requests == 0 for status in statuses.values())
    assert all(status.healthy for status in statuses.values())
    assert all(instance.ping_calls == 1 for instance in instances.values())


def test_nonstrict_warm_reports_failure_without_hiding_other_helpers(tmp_path: Path) -> None:
    registry, _instances, _factory_calls = _registry(
        tmp_path,
        failing="vector",
    )

    statuses = registry.warm(strict=False)

    assert statuses["observability"].healthy is True
    assert statuses["physics"].healthy is True
    assert statuses["retrieval"].healthy is True
    assert statuses["vector"].healthy is False
    assert statuses["vector"].failed_requests >= 1
    assert statuses["vector"].last_error == "RuntimeError"


def test_nonstrict_warm_redacts_exception_payload(tmp_path: Path) -> None:
    registry, instances, _factory_calls = _registry(tmp_path)

    def leaking_ping() -> int:
        raise RuntimeError("token=super-secret-value")

    instances["vector"].ping = leaking_ping  # type: ignore[method-assign]
    statuses = registry.warm("vector", strict=False)

    assert statuses["vector"].last_error == "RuntimeError"
    assert "super-secret-value" not in (statuses["vector"].last_error or "")


def test_strict_warm_raises_aggregated_registry_error(tmp_path: Path) -> None:
    registry, _instances, _factory_calls = _registry(
        tmp_path,
        failing="physics",
    )

    with pytest.raises(JvmAcceleratorRegistryError, match="physics"):
        registry.warm(strict=True)


def test_restart_is_explicit_and_updates_runtime_status(tmp_path: Path) -> None:
    registry, instances, _factory_calls = _registry(tmp_path)
    registry.warm("observability")

    status = registry.restart("observability")

    assert instances["observability"].restart_calls == 1
    assert status.running is True
    assert status.restarts == 1
    assert status.starts == 2
    assert status.requests == 2


def test_close_releases_only_selected_instance(tmp_path: Path) -> None:
    registry, instances, factory_calls = _registry(tmp_path)
    registry.warm()

    registry.close("vector")

    assert instances["vector"].close_calls == 1
    assert instances["observability"].close_calls == 0
    assert registry.initialized("vector") is False
    assert registry.initialized("observability") is True

    # A later get creates a new registry entry through the factory seam.
    assert registry.get("vector") is instances["vector"]
    assert factory_calls["vector"] == 2


def test_context_manager_closes_initialized_helpers(tmp_path: Path) -> None:
    registry, instances, _factory_calls = _registry(tmp_path)

    with registry:
        registry.warm("physics")
        assert instances["physics"].running is True

    assert instances["physics"].close_calls == 1
    assert instances["physics"].running is False
    assert registry.initialized("physics") is False


def test_health_probe_uses_preflight_without_initializing_java(tmp_path: Path) -> None:
    registry, _instances, factory_calls = _registry(tmp_path)

    result = registry.health_probe("vector")()

    assert result.name == "jvm.vector"
    assert result.ok is True
    assert result.detail == "preflight ready"
    assert result.metadata["initialized"] is False
    assert factory_calls["vector"] == 0


def test_health_probe_can_require_an_already_running_helper(tmp_path: Path) -> None:
    registry, _instances, _factory_calls = _registry(tmp_path)
    probe = registry.health_probe("physics", require_running=True)

    before = probe()
    registry.warm("physics")
    after = probe()

    assert before.ok is False
    assert "not running" in before.detail
    assert after.ok is True
    assert after.detail == "running"
    assert after.metadata["requests"] == 1


def test_health_probe_reports_missing_source_without_starting_factory(tmp_path: Path) -> None:
    factory_calls = {"vector": 0}

    def factory() -> _FakeAccelerator:
        factory_calls["vector"] += 1
        return _FakeAccelerator("vector")

    missing = tmp_path / "missing.java"
    registry = JvmAcceleratorRegistry(
        factories={"vector": factory},
        config_providers={
            "vector": lambda: SimpleNamespace(
                java_binary=sys.executable,
                source=missing,
            )
        },
    )

    result = registry.health_probe("vector")()

    assert result.ok is False
    assert "unavailable" in result.detail
    assert factory_calls["vector"] == 0


def test_unknown_names_fail_closed(tmp_path: Path) -> None:
    registry, _instances, _factory_calls = _registry(tmp_path)

    with pytest.raises(JvmAcceleratorRegistryError, match="unknown"):
        registry.get("database")
    with pytest.raises(JvmAcceleratorRegistryError, match="unknown"):
        registry.preflight("database")
    with pytest.raises(JvmAcceleratorRegistryError, match="unknown"):
        registry.close("database")


def test_bad_registry_configuration_rejects_unknown_factory_name() -> None:
    with pytest.raises(JvmAcceleratorRegistryError, match="unknown"):
        JvmAcceleratorRegistry(
            factories={"unknown": lambda: object()},
        )
