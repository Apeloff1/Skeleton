"""Operational registry for Skeleton's optional JVM batch accelerators.

This module deliberately does not participate in domain ownership. It provides
one place to preflight, warm, inspect, restart, and close the optional Java
helpers used by observability, dense retrieval, and physics.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from skeleton.native.jvm_protocol import JvmCapability, capability_for
from skeleton.native.profiling import source_identity
from skeleton.native.selection import (
    ProfileEvidence,
    evaluate_candidate,
    policy_from_mapping,
)

_ACCELERATOR_NAMES = ("observability", "vector", "physics")
_JVM_CANDIDATE_IDS = {
    "observability": "ACCEL-JVM-OBSERVABILITY",
    "vector": "ACCEL-JVM-VECTOR",
    "physics": "ACCEL-JVM-PHYSICS",
}
_PROFILE_SELECTED_STATE = "profile_selected_unpromoted"
_JVM_PROTOCOL = "skeleton.acceleration.rpc@1.0"


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
    capability_digest: str = ""
    protocol_versions: tuple[int, ...] = ()
    minimum_java_major: int = 0

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


@dataclass(frozen=True, slots=True)
class JvmAccelerationSelection:
    """Revalidated profile-selection state for one JVM accelerator."""

    name: str
    candidate_id: str
    selected: bool
    reasons: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_identity: str | None = None
    policy_path: str | None = None

    def __post_init__(self) -> None:
        if self.name not in _ACCELERATOR_NAMES:
            raise ValueError("invalid JVM accelerator selection name")
        if self.candidate_id != _JVM_CANDIDATE_IDS[self.name]:
            raise ValueError("JVM accelerator candidate identity mismatch")
        if not isinstance(self.selected, bool):
            raise TypeError("selected must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, str) or not reason
            for reason in self.reasons
        ):
            raise ValueError("selection reasons must be non-empty strings")
        if self.selected and self.reasons:
            raise ValueError("selected JVM accelerator cannot carry rejection reasons")


ConfigProvider = Callable[[], Any]
AcceleratorFactory = Callable[[], Any]
SelectionProvider = Callable[[str], JvmAccelerationSelection]


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


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite JSON token rejected: {token}")


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON object key: {key}")
        output[key] = value
    return output


def _load_acceleration_policy(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(
        raw,
        object_pairs_hook=_strict_object_pairs,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(payload, dict):
        raise ValueError("acceleration policy must be an object")
    return payload


def _profile_evidence_from_mapping(raw: Mapping[str, Any]) -> ProfileEvidence:
    return ProfileEvidence(
        evidence_id=raw["evidence_id"],
        candidate_id=raw["candidate_id"],
        source_identity=raw["source_identity"],
        environment_id=raw["environment_id"],
        sample_count=raw["sample_count"],
        reference_median_ns=raw["reference_median_ns"],
        candidate_median_ns=raw["candidate_median_ns"],
        correctness_passed=raw["correctness_passed"],
        max_abs_error=raw["max_abs_error"],
        crash_count=raw.get("crash_count", 0),
        timeout_count=raw.get("timeout_count", 0),
    )


def _default_selection_provider(name: str) -> JvmAccelerationSelection:
    candidate_id = _JVM_CANDIDATE_IDS[name]
    root = Path(__file__).resolve().parents[2]
    configured = os.environ.get("SKELETON_ACCELERATION_POLICY_PATH")
    policy_path = (
        Path(configured).expanduser()
        if configured
        else root / "machine" / "acceleration_policy.json"
    )
    policy_path_text = str(policy_path)

    if not policy_path.is_file():
        return JvmAccelerationSelection(
            name=name,
            candidate_id=candidate_id,
            selected=False,
            reasons=("policy-unavailable",),
            policy_path=policy_path_text,
        )

    try:
        policy = _load_acceleration_policy(policy_path)
        candidates = policy["candidates"]
        if not isinstance(candidates, list):
            raise ValueError("candidates must be a list")
        matches = [
            item
            for item in candidates
            if isinstance(item, dict) and item.get("id") == candidate_id
        ]
        if len(matches) != 1:
            raise ValueError("candidate identity must resolve exactly once")
        candidate = matches[0]
        if candidate.get("plane") != "jvm":
            raise ValueError("candidate plane must be jvm")
        if candidate.get("registry") != "skeleton/native/jvm_registry.py":
            raise ValueError("candidate registry authority drift")

        identity_paths = candidate.get("source_identity_paths")
        if not isinstance(identity_paths, list) or not identity_paths:
            raise ValueError("candidate source identity paths are required")
        current_identity = source_identity(root, identity_paths)

        raw_evidence = candidate.get("profile_evidence", [])
        if not isinstance(raw_evidence, list):
            raise ValueError("candidate profile_evidence must be a list")
        evidence = tuple(
            _profile_evidence_from_mapping(item)
            for item in raw_evidence
            if isinstance(item, Mapping)
        )
        if len(evidence) != len(raw_evidence):
            raise ValueError("candidate profile evidence entry must be an object")

        selection_policy = policy_from_mapping(policy["selection_policy"])
        refs = candidate.get("reference_paths")
        if not isinstance(refs, list) or not refs:
            raise ValueError("candidate reference paths are required")
        reference_available = all((root / Path(path)).exists() for path in refs)
        isolation_satisfied = candidate.get("isolation") == "subprocess"
        capability = capability_for(name)
        protocol_compatible = (
            candidate.get("protocol") == _JVM_PROTOCOL
            and 1 in capability.protocol_versions
        )
        decision = evaluate_candidate(
            candidate_id=candidate_id,
            current_source_identity=current_identity,
            reference_available=reference_available,
            isolation_satisfied=isolation_satisfied,
            protocol_compatible=protocol_compatible,
            evidence=evidence,
            policy=selection_policy,
        )

        persisted = candidate.get("selection_decision")
        reasons = list(decision.reason_codes)
        if candidate.get("automatic_selection") is not True:
            reasons.append("automatic-selection-disabled")
        if candidate.get("state") != _PROFILE_SELECTED_STATE:
            reasons.append("candidate-state-not-selected")
        if not isinstance(persisted, Mapping):
            reasons.append("persisted-selection-missing")
        else:
            expected_ids = tuple(sorted(decision.evidence_ids))
            persisted_ids = persisted.get("evidence_ids")
            if (
                persisted.get("qualified") is not True
                or persisted.get("route") != "accelerated"
                or persisted.get("effective_route") != "accelerated"
                or persisted.get("source_identity") != current_identity
                or not isinstance(persisted_ids, list)
                or tuple(sorted(persisted_ids)) != expected_ids
            ):
                reasons.append("persisted-selection-drift")

        normalized = tuple(sorted(set(reasons)))
        return JvmAccelerationSelection(
            name=name,
            candidate_id=candidate_id,
            selected=not normalized,
            reasons=normalized,
            evidence_ids=tuple(sorted(decision.evidence_ids)),
            source_identity=current_identity,
            policy_path=policy_path_text,
        )
    except Exception:
        return JvmAccelerationSelection(
            name=name,
            candidate_id=candidate_id,
            selected=False,
            reasons=("policy-invalid",),
            policy_path=policy_path_text,
        )


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
        selection_provider: SelectionProvider | None = None,
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
        self._selection_provider = selection_provider or _default_selection_provider
        self._lock = threading.RLock()

    @property
    def names(self) -> tuple[str, ...]:
        return _ACCELERATOR_NAMES

    def initialized(self, name: str) -> bool:
        self._validate_name(name)
        with self._lock:
            return name in self._instances

    def capability(self, name: str) -> JvmCapability:
        self._validate_name(name)
        return capability_for(name)

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
            capability = self.capability(item)
            output[item] = JvmAcceleratorPreflight(
                name=item,
                java_binary=java_binary,
                java_path=java_path,
                source=str(source),
                java_available=java_path is not None,
                source_available=source.is_file(),
                capability_digest=capability.capability_digest,
                protocol_versions=capability.protocol_versions,
                minimum_java_major=capability.minimum_java_major,
            )
        return output

    def selection(self, name: str) -> JvmAccelerationSelection:
        """Return fail-closed profile-selection state without starting Java."""
        self._validate_name(name)
        decision = self._selection_provider(name)
        if not isinstance(decision, JvmAccelerationSelection):
            raise JvmAcceleratorRegistryError(
                "selection provider returned invalid decision"
            )
        if decision.name != name:
            raise JvmAcceleratorRegistryError(
                "selection provider returned mismatched accelerator"
            )
        return decision

    def get(self, name: str) -> Any:
        """Return a raw lazy helper for diagnostics, tests, or explicit operators."""
        self._validate_name(name)
        with self._lock:
            instance = self._instances.get(name)
            if instance is None:
                instance = self._factories[name]()
                self._instances[name] = instance
            return instance

    def get_selected(self, name: str) -> Any:
        """Return a helper only after canonical profile policy selects it."""
        decision = self.selection(name)
        if not decision.selected:
            detail = ",".join(decision.reasons) or "not-selected"
            raise JvmAcceleratorRegistryError(
                f"{name} JVM accelerator is not profile-selected: {detail}"
            )
        return self.get(name)

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


_default_registry: JvmAcceleratorRegistry | None = None
_default_registry_lock = threading.Lock()


def get_default_jvm_registry() -> JvmAcceleratorRegistry:
    """Return the single process-wide JVM accelerator lifecycle owner.

    Domain compatibility getters delegate here instead of maintaining their
    own singleton process references. The registry remains lazy: obtaining it
    does not construct or start an accelerator.
    """
    global _default_registry
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = JvmAcceleratorRegistry()
        return _default_registry


def close_default_jvm_accelerator(name: str) -> None:
    """Close one default-registry helper without materializing the registry."""
    JvmAcceleratorRegistry._validate_name(name)
    with _default_registry_lock:
        registry = _default_registry
    if registry is not None:
        registry.close(name)


def close_default_jvm_registry() -> None:
    """Close every initialized JVM helper owned by the default registry."""
    global _default_registry
    with _default_registry_lock:
        registry = _default_registry
        _default_registry = None
    if registry is not None:
        registry.close()


atexit.register(close_default_jvm_registry)


__all__ = [
    "JvmAccelerationSelection",
    "JvmAcceleratorPreflight",
    "JvmAcceleratorRegistry",
    "JvmAcceleratorRegistryError",
    "JvmAcceleratorRuntimeStatus",
    "close_default_jvm_accelerator",
    "close_default_jvm_registry",
    "get_default_jvm_registry",
]
