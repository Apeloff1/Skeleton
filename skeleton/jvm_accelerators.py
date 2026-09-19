"""Operational registry for Skeleton's optional JVM batch accelerators.

This module deliberately does not participate in domain ownership. It provides
one place to preflight, warm, inspect, restart, and close the optional Java
helpers used by observability, dense retrieval, and physics.
"""
from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

_ACCELERATOR_NAMES = ("observability", "vector", "physics")


class JvmAcceleratorRegistryError(RuntimeError):
    """Raised for invalid registry operations or strict warm failures."""


@dataclass(frozen=True, slots=True)
class JvmAcceleratorPreflight:
    name: str
    java_binary: str
    java_path: str | None
    source: str
    java_available: bool
    source_available: bool

    @property
    def ready(self) -> bool:
        return self.java_available and self.source_available


@dataclass(frozen=True, slots=True)
class JvmAcceleratorRuntimeStatus:
    name: str
    initialized: bool
    running: bool
    closed: bool
    java_binary: str
    source: str
    java_available: bool
    source_available: bool
    pid: int | None = None
    server_processors: int | None = None
    starts: int = 0
    start_failures: int = 0
    restarts: int = 0
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeouts: int = 0
    last_error: str | None = None

    @property
    def healthy(self) -> bool:
        if self.last_error is not None:
            return False
        if self.initialized:
            return self.running and not self.closed
        return self.java_available and self.source_available


ConfigProvider = Callable[[], Any]
AcceleratorFactory = Callable[[], Any]


def _default_config_provider(name: str) -> ConfigProvider:
    if name == "observability":
        def provider() -> Any:
            from skeleton.observability.jvm_accelerator import JvmAcceleratorConfig
            return JvmAcceleratorConfig.discover()
        return provider
    if name == "vector":
        def provider() -> Any:
            from skeleton.memory.jvm_vector_accelerator import JvmVectorConfig
            return JvmVectorConfig.discover()
        return provider
    if name == "physics":
        def provider() -> Any:
            from skeleton.simulation.physics.jvm_broadphase_accelerator import (
                JvmBroadPhaseConfig,
            )
            return JvmBroadPhaseConfig.discover()
        return provider
    raise JvmAcceleratorRegistryError(f"unknown JVM accelerator: {name}")


def _default_factory(name: str) -> AcceleratorFactory:
    if name == "observability":
        def factory() -> Any:
            from skeleton.observability.jvm_accelerator import (
                JvmObservabilityAccelerator,
            )
            return JvmObservabilityAccelerator()
        return factory
    if name == "vector":
        def factory() -> Any:
            from skeleton.memory.jvm_vector_accelerator import JvmVectorAccelerator
            return JvmVectorAccelerator()
        return factory
    if name == "physics":
        def factory() -> Any:
            from skeleton.simulation.physics.jvm_broadphase_accelerator import (
                JvmBroadPhaseAccelerator,
            )
            return JvmBroadPhaseAccelerator()
        return factory
    raise JvmAcceleratorRegistryError(f"unknown JVM accelerator: {name}")


def _resolve_java(binary: str) -> str | None:
    if not binary:
        return None
    if os.path.sep in binary:
        path = Path(binary)
        return str(path) if path.is_file() else None
    return shutil.which(binary)


class JvmAcceleratorRegistry:
    """Lazy manager for the three optional JVM helpers.

    Constructing the registry, calling :meth:`preflight`, or calling
    :meth:`get` do not start Java. get() only constructs the lazy Python
    wrapper. A helper process starts when :meth:`warm` pings it or when a
    domain object invokes an accelerator operation.
    """

    def __init__(
        self,
        *,
        factories: Mapping[str, AcceleratorFactory] | None = None,
        config_providers: Mapping[str, ConfigProvider] | None = None,
    ) -> None:
        supplied_factories = dict(factories or {})
        supplied_configs = dict(config_providers or {})
        unknown = (
            set(supplied_factories)
            | set(supplied_configs)
        ) - set(_ACCELERATOR_NAMES)
        if unknown:
            raise JvmAcceleratorRegistryError(
                f"unknown JVM accelerators: {sorted(unknown)!r}"
            )

        self._factories: dict[str, AcceleratorFactory] = {
            name: supplied_factories.get(name, _default_factory(name))
            for name in _ACCELERATOR_NAMES
        }
        self._config_providers: dict[str, ConfigProvider] = {
            name: supplied_configs.get(name, _default_config_provider(name))
            for name in _ACCELERATOR_NAMES
        }
        self._instances: dict[str, Any] = {}
        self._lock = threading.RLock()

    @property
    def names(self) -> tuple[str, ...]:
        return _ACCELERATOR_NAMES

    def initialized(self, name: str) -> bool:
        self._validate_name(name)
        with self._lock:
            return name in self._instances

    def preflight(
        self,
        name: str | None = None,
    ) -> dict[str, JvmAcceleratorPreflight]:
        names = self._select(name)
        output: dict[str, JvmAcceleratorPreflight] = {}
        for item in names:
            config = self._config_providers[item]()
            java_binary = str(getattr(config, "java_binary", ""))
            source = Path(getattr(config, "source"))
            java_path = _resolve_java(java_binary)
            output[item] = JvmAcceleratorPreflight(
                name=item,
                java_binary=java_binary,
                java_path=java_path,
                source=str(source),
                java_available=java_path is not None,
                source_available=source.is_file(),
            )
        return output

    def get(self, name: str) -> Any:
        self._validate_name(name)
        with self._lock:
            instance = self._instances.get(name)
            if instance is None:
                instance = self._factories[name]()
                self._instances[name] = instance
            return instance

    def warm(
        self,
        name: str | None = None,
        *,
        strict: bool = True,
    ) -> dict[str, JvmAcceleratorRuntimeStatus]:
        failures: dict[str, str] = {}
        for item in self._select(name):
            accelerator = self.get(item)
            try:
                accelerator.ping()
            except Exception as exc:
                from skeleton.observability.redaction import safe_exception_text

                failures[item] = safe_exception_text(exc)

        statuses = self.status(name)
        if failures and strict:
            detail = "; ".join(
                f"{item}={message}"
                for item, message in sorted(failures.items())
            )
            raise JvmAcceleratorRegistryError(
                f"JVM accelerator warm failed: {detail}"
            )
        if failures:
            statuses = {
                item: (
                    self._with_error(status, failures[item])
                    if item in failures
                    else status
                )
                for item, status in statuses.items()
            }
        return statuses

    def health_probe(
        self,
        name: str,
        *,
        require_running: bool = False,
    ) -> Callable[[], Any]:
        """Build a HealthRegistry-compatible probe without starting Java.

        If require_running is false, an uninitialized helper is healthy when
        its Java binary and source file pass preflight. If true, the probe
        requires an already-initialized, currently running helper.
        """
        self._validate_name(name)

        def run() -> Any:
            import time
            from skeleton.observability.health import ProbeResult

            started = time.perf_counter()
            try:
                status = self.status(name)[name]
                if require_running:
                    ok = (
                        status.initialized
                        and status.running
                        and not status.closed
                        and status.last_error is None
                    )
                    detail = (
                        "running"
                        if ok
                        else "JVM accelerator is not running"
                    )
                else:
                    ok = status.healthy
                    if status.initialized:
                        detail = (
                            "running"
                            if ok
                            else status.last_error
                            or "JVM accelerator runtime unhealthy"
                        )
                    else:
                        detail = (
                            "preflight ready"
                            if ok
                            else "Java binary or accelerator source unavailable"
                        )
                return ProbeResult(
                    name=f"jvm.{name}",
                    ok=ok,
                    detail=detail,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    metadata={
                        "initialized": status.initialized,
                        "running": status.running,
                        "starts": status.starts,
                        "start_failures": status.start_failures,
                        "requests": status.requests,
                        "failed_requests": status.failed_requests,
                    },
                )
            except Exception as exc:
                from skeleton.observability.redaction import safe_exception_text

                return ProbeResult(
                    name=f"jvm.{name}",
                    ok=False,
                    detail=safe_exception_text(exc),
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                )

        return run

    def restart(self, name: str) -> JvmAcceleratorRuntimeStatus:
        self._validate_name(name)
        with self._lock:
            accelerator = self.get(name)
            restart = getattr(accelerator, "restart", None)
            if not callable(restart):
                raise JvmAcceleratorRegistryError(
                    f"{name} accelerator does not support restart"
                )
            restart()
        return self.status(name)[name]

    def close(self, name: str | None = None) -> None:
        selected = self._select(name)
        with self._lock:
            for item in selected:
                accelerator = self._instances.pop(item, None)
                if accelerator is None:
                    continue
                close = getattr(accelerator, "close", None)
                if callable(close):
                    close()

    def status(
        self,
        name: str | None = None,
    ) -> dict[str, JvmAcceleratorRuntimeStatus]:
        preflight = self.preflight(name)
        output: dict[str, JvmAcceleratorRuntimeStatus] = {}
        for item in self._select(name):
            probe = preflight[item]
            with self._lock:
                accelerator = self._instances.get(item)
            if accelerator is None:
                output[item] = JvmAcceleratorRuntimeStatus(
                    name=item,
                    initialized=False,
                    running=False,
                    closed=False,
                    java_binary=probe.java_binary,
                    source=probe.source,
                    java_available=probe.java_available,
                    source_available=probe.source_available,
                )
                continue

            status_method = getattr(accelerator, "status", None)
            if not callable(status_method):
                raise JvmAcceleratorRegistryError(
                    f"{item} accelerator does not expose status"
                )
            raw = status_method()
            output[item] = JvmAcceleratorRuntimeStatus(
                name=item,
                initialized=True,
                running=bool(getattr(raw, "running", False)),
                closed=bool(getattr(raw, "closed", False)),
                java_binary=str(
                    getattr(raw, "java_binary", probe.java_binary)
                ),
                source=str(getattr(raw, "source", probe.source)),
                java_available=probe.java_available,
                source_available=probe.source_available,
                pid=getattr(raw, "pid", None),
                server_processors=getattr(
                    raw,
                    "server_processors",
                    None,
                ),
                starts=int(getattr(raw, "starts", 0)),
                start_failures=int(getattr(raw, "start_failures", 0)),
                restarts=int(getattr(raw, "restarts", 0)),
                requests=int(getattr(raw, "requests", 0)),
                successful_requests=int(
                    getattr(raw, "successful_requests", 0)
                ),
                failed_requests=int(
                    getattr(raw, "failed_requests", 0)
                ),
                timeouts=int(getattr(raw, "timeouts", 0)),
                last_error=getattr(raw, "last_error", None),
            )
        return output

    def __enter__(self) -> "JvmAcceleratorRegistry":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _with_error(
        status: JvmAcceleratorRuntimeStatus,
        error: str,
    ) -> JvmAcceleratorRuntimeStatus:
        return JvmAcceleratorRuntimeStatus(
            name=status.name,
            initialized=status.initialized,
            running=status.running,
            closed=status.closed,
            java_binary=status.java_binary,
            source=status.source,
            java_available=status.java_available,
            source_available=status.source_available,
            pid=status.pid,
            server_processors=status.server_processors,
            starts=status.starts,
            start_failures=status.start_failures,
            restarts=status.restarts,
            requests=status.requests,
            successful_requests=status.successful_requests,
            failed_requests=max(1, status.failed_requests),
            timeouts=status.timeouts,
            last_error=error,
        )

    @staticmethod
    def _validate_name(name: str) -> None:
        if name not in _ACCELERATOR_NAMES:
            raise JvmAcceleratorRegistryError(
                f"unknown JVM accelerator: {name}"
            )

    @classmethod
    def _select(cls, name: str | None) -> tuple[str, ...]:
        if name is None:
            return _ACCELERATOR_NAMES
        cls._validate_name(name)
        return (name,)


__all__ = [
    "JvmAcceleratorPreflight",
    "JvmAcceleratorRegistry",
    "JvmAcceleratorRegistryError",
    "JvmAcceleratorRuntimeStatus",
]
