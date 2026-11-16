"""Measured CPU admission at the canonical protected llama.cpp activation boundary.

The old Jeeves compatibility bridge remains fail-closed. This factory accepts
only trusted application-owned protection dependencies and an independently
pinned deployment and weight plan. It installs the existing native rejection
hook, without replacing provider authorization, context protection or artifact
verification.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import threading
import time

from skeleton.ai.runtime.inference.deployment import LocalModelDeployment, LocalModelDeploymentError
from skeleton.ai.runtime.inference.guarded_composition import ProtectedLocalComponents
from skeleton.ai.runtime.inference.llama_cpp import (
    COMPLETION_CHAT_FLAGS, QWEN3_COMPLETION_CHAT_TEMPLATE, LlamaCppModel, LlamaCppRuntimeError,
)
from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController
from skeleton.app.offline_cpu_budget import MemoryTopology
from skeleton.app.offline_native_process_lease import NativeCpuLeaseOwner, NativeLeaseError
from skeleton.ai.runtime.inference.local import LocalModelAdapter, sample_serving_resources
from skeleton.app.offline_runtime_preflight import (
    ModelSource, RuntimePolicy, RuntimePreflightError, canonical, digest, identity, inspect_source,
    plan_preflight, require, sample_hardware, integer,
)

SCHEMA = "skeleton.offline.measured-llama-cpu.v1"


class MeasuredLlamaCpuGate:
    """Reject unsafe native launches using live host measurements.

    A single-process canonical engine is mandatory. The budget includes
    the native owner's explicit context-wide KV estimate and scratch, the
    independently pinned weight bytes, and the operator's base reserves.
    This is not an OS memory reservation or system-wide concurrency lock.
    """

    def __init__(self, backend: LlamaCppModel, source: ModelSource,
                 policy: RuntimePolicy) -> None:
        require(type(backend) is LlamaCppModel, "canonical llama.cpp backend required")
        require(isinstance(source, ModelSource) and isinstance(policy, RuntimePolicy),
                "verified source and explicit runtime policy required")
        require(policy.backend == "cpu" and policy.verify_gguf_headers,
                "measured native gate requires CPU and GGUF framing")
        config = backend.config
        require(config.gpu_layers == 0 and config.kv_cache_location in ("backend", "host"),
                "measured CPU gate cannot authorize device offload")
        permitted = ((), tuple(COMPLETION_CHAT_FLAGS),
                     tuple(COMPLETION_CHAT_FLAGS) + ("--chat-template", QWEN3_COMPLETION_CHAT_TEMPLATE))
        require(config.extra_args in permitted and not config.environment,
                "measured CPU gate requires a fixed native argument profile")
        require(config.threads is not None and config.context_size is not None,
                "explicit native thread and context limits required")
        require(config.rehash_artifacts_each_run,
                "native source must be rehashed at each execution")
        require(len(source.plan.shards) == 1 and len(source.headers) == 1,
                "single GGUF deployment requires exactly one verified shard")
        shard = source.plan.shards[0]
        require(shard.digest == backend.model_artifact.sha256 == backend.model_digest
                and shard.bytes == backend.model_artifact.size_bytes,
                "native artifact differs from verified source bytes")
        kv_upper = backend.serving_metadata.kv_bytes_per_token_upper_bound
        # The operator may enlarge the estimate, but not override a known
        # upper bound downwards. With neither estimate, execution is denied.
        estimates = [n for n in (config.kv_bytes_per_token, kv_upper) if n is not None]
        require(bool(estimates) and max(estimates) > 0, "native KV estimate unavailable")
        kv_reserve = config.context_size * max(estimates)
        scratch = config.runtime_scratch_bytes
        self._policy = replace(policy, host_reserve_bytes=policy.host_reserve_bytes + kv_reserve + scratch)
        self._source = source
        self._backend = backend
        self._source_digest = digest(source.snapshot())
        self._model_digest = backend.model_digest
        self._runtime_digest = backend.runtime_digest
        self._profile = backend.execution_profile_digest
        self._threads = config.threads
        self._kv_reserve = kv_reserve
        self._scratch = scratch
        self._lock = threading.RLock()
        self._sequence = 0
        self._last = None
        self._closed = False
        self._lease_owner: NativeCpuLeaseOwner | None = None

    def bind_native_lease(self, directory: Path) -> None:
        """Bind an optional shared local slot before any check or launch."""
        with self._lock:
            require(not self._closed and self._sequence == 0 and self._lease_owner is None,
                    "native lease must be bound before admission")
            try:
                owner = NativeCpuLeaseOwner(directory, self)
                self._backend.install_resource_lease_factory(owner.acquire)
            except NativeLeaseError as exc:
                raise RuntimePreflightError("shared native lease unavailable") from exc
            self._lease_owner = owner

    def __call__(self) -> None:
        """Record the latest rejection even when an evidence collector fails."""
        with self._lock:
            self._sequence += 1
            self._last = None
            try:
                self._check()
            except BaseException:
                if self._last is None:
                    body = {
                        "schema": SCHEMA, "sequence": self._sequence,
                        "source_digest": self._source_digest, "model_digest": self._model_digest,
                        "runtime_digest": self._runtime_digest, "execution_profile_digest": self._profile,
                        "checked_ns": time.monotonic_ns(), "threads": self._threads,
                        "kv_reserve_bytes": self._kv_reserve, "scratch_reserve_bytes": self._scratch,
                        "worker_ceiling": 0, "preflight_digest": None,
                        "blockers": ["native_evidence_check_failed"], "status": "blocked",
                        "native_qualified": False, "release_qualified": False,
                    }
                    self._last = {**body, "gate_digest": digest(body)}
                raise

    def _check(self) -> None:
        require(not self._closed, "measured native gate closed")
        require(digest(self._source.snapshot()) == self._source_digest,
                "runtime source evidence changed")
        require((self._backend.model_digest, self._backend.runtime_digest,
                 self._backend.execution_profile_digest) ==
                (self._model_digest, self._runtime_digest, self._profile),
                "native execution profile changed")
        reading = sample_hardware()
        require(reading.origin == "local_probe", "real local probe required")
        # The canonical inference engine probe follows nested cgroups,
        # Windows commit limits and pressure signals. Do not count host
        # free memory that its scoped probe cannot actually allocate.
        serving = sample_serving_resources(fresh=True)
        scoped = serving.allocation_headroom_bytes
        available = reading.memory.available_bytes
        if scoped is None or available is None or serving.available_memory_bytes is None:
            available = None
        else:
            available = min(scoped, available)
        reading = replace(reading, memory=MemoryTopology(
            reading.memory.total_bytes, available, "intersection-with-serving-headroom"))
        now = time.monotonic_ns()
        planned = plan_preflight(self._source, reading, self._policy, now_ns=now)
        # Fresh classification per invocation: the canonical controller
        # throttles consecutive samples internally, which must not hide
        # a critical observation at the actual child-spawn boundary.
        pressure = AdaptiveServingController(1)
        pressure.update(serving, now=now / 1_000_000_000, queued=0)
        # Treat the canonical energy-reduced worker ceiling as a
        # conservative maximum for native threads. An already activated
        # runtime must not silently rewrite its pinned execution profile.
        admitted = (planned["status"] == "candidate" and planned["worker_ceiling"] >= self._threads
                    and pressure.level != "critical")
        blockers = list(planned["blockers"])
        if pressure.level == "critical":
            blockers.append("canonical_serving_" + pressure.reason)
        if planned["worker_ceiling"] < self._threads:
            blockers.append("native_thread_ceiling_exceeded")
        body = {"schema": SCHEMA, "sequence": self._sequence,
                "source_digest": self._source_digest, "model_digest": self._model_digest,
                "runtime_digest": self._runtime_digest, "execution_profile_digest": self._profile,
                "preflight_digest": planned["preflight_digest"], "checked_ns": now,
                "serving_observation_digest": digest(serving.as_dict()),
                "serving_pressure": pressure.level, "serving_reason": pressure.reason,
                "threads": self._threads, "worker_ceiling": planned["worker_ceiling"],
                "kv_reserve_bytes": self._kv_reserve, "scratch_reserve_bytes": self._scratch,
                "blockers": blockers, "status": "candidate" if admitted else "blocked",
                "native_qualified": False, "release_qualified": False}
        self._last = {**body, "gate_digest": digest(body)}
        require(admitted, "measured CPU native launch denied")

    def status(self) -> dict:
        with self._lock:
            import json
            result = {"closed": self._closed, "checks": self._sequence,
                      "last": json.loads(canonical(self._last)),
                      "native_qualified": False, "release_qualified": False}
            owner = self._lease_owner
        # acquire() takes the lease lock before calling this gate. Do not
        # reverse that order when reading diagnostics.
        result["shared_native_lease"] = owner.status() if owner is not None else None
        return result

    def close(self) -> None:
        with self._lock:
            self._closed = True


def _resolve_measured_source(
    manifest_path: Path, *, manifest_digest: str, manifest_sha256: str,
    maximum_deployment_bytes: int, store_path: Path,
    plan_digest: str, model_identity_digest: str, policy: RuntimePolicy,
) -> tuple[LocalModelDeployment, ModelSource]:
    identity(manifest_digest, "deployment digest")
    identity(manifest_sha256, "raw deployment manifest SHA")
    integer(maximum_deployment_bytes, 1, 1 << 40, "deployment byte limit")
    require(isinstance(policy, RuntimePolicy) and policy.backend == "cpu" and policy.verify_gguf_headers,
            "measured protected CPU policy required")
    deployment = LocalModelDeployment.load(manifest_path, expected_sha256=manifest_sha256,
                                          max_artifact_bytes=maximum_deployment_bytes)
    require(deployment.manifest_digest == manifest_digest, "independent deployment pin mismatch")
    source = inspect_source(store_path, plan_digest=plan_digest,
                            model_identity_digest=model_identity_digest, policy=policy)
    require(len(source.plan.shards) == 1 and
            source.plan.shards[0].digest == deployment.model_sha256,
            "deployment and independently verified store disagree")
    return deployment, source


def build_measured_guarded_deployment(
    manifest_path: Path, *, manifest_digest: str, manifest_sha256: str,
    maximum_deployment_bytes: int, store_path: Path,
    plan_digest: str, model_identity_digest: str,
    policy: RuntimePolicy, components: ProtectedLocalComponents,
    default_seed: int = 0, max_queue_size: int = 256, max_batch_size: int = 256,
    lease_directory: Path | None = None,
) -> tuple[LocalModelAdapter, MeasuredLlamaCpuGate]:
    """Trusted startup composition; callers route through the protected adapter.

    No persisted JSON may choose a protection component, select a fallback,
    or downgrade guarded execution. The deployment verifies its runtime and
    GGUF independently before the additional measured gate is installed.
    Cache is disabled and concurrency is one for this initial CPU profile.
    """
    require(isinstance(components, ProtectedLocalComponents), "trusted protection components required")
    deployment, source = _resolve_measured_source(
        manifest_path, manifest_digest=manifest_digest, manifest_sha256=manifest_sha256,
        maximum_deployment_bytes=maximum_deployment_bytes, store_path=store_path,
        plan_digest=plan_digest, model_identity_digest=model_identity_digest, policy=policy,
    )
    adapter = deployment.adapter(cache_size=0, default_seed=default_seed, rehash_artifacts_each_run=True,
                                 max_concurrency=1, max_queue_size=max_queue_size,
                                 max_batch_size=max_batch_size, require_guarded_inference=True,
                                 guarded_components=components)
    require(adapter.require_guarded_inference and adapter.guarded_service is not None,
            "protected adapter is required")
    gate = MeasuredLlamaCpuGate(adapter.engine.model, source, policy)
    # The native backend already calls this before prompt handling AND at
    # process spawn. It rejects hook replacement or late installation.
    adapter.engine.model.install_prelaunch_resource_guard(gate)
    if lease_directory is not None:
        gate.bind_native_lease(lease_directory)
    return adapter, gate


@dataclass(frozen=True, slots=True)
class MeasuredLocalDeployment:
    """Trusted startup-only configuration, not an environment or request parser."""

    manifest_digest: str
    manifest_sha256: str
    maximum_deployment_bytes: int
    store_path: Path
    plan_digest: str
    model_identity_digest: str
    policy: RuntimePolicy
    lease_directory: Path | None = None

    def __post_init__(self) -> None:
        for name in ("manifest_digest", "manifest_sha256", "plan_digest", "model_identity_digest"):
            identity(getattr(self, name), name)
        integer(self.maximum_deployment_bytes, 1, 1 << 40, "deployment byte limit")
        require(isinstance(self.store_path, Path) and self.store_path.is_absolute(),
                "explicit absolute weight store path required")
        require(isinstance(self.policy, RuntimePolicy) and self.policy.backend == "cpu"
                and self.policy.verify_gguf_headers, "measured protected CPU policy required")
        require(self.lease_directory is None or (isinstance(self.lease_directory, Path)
                and self.lease_directory.is_absolute()), "absolute shared lease directory required")

    def activate(self, manifest_path: str | Path, *, components: ProtectedLocalComponents,
                 default_seed: int, max_queue_size: int, max_batch_size: int
                 ) -> tuple[LocalModelAdapter, MeasuredLlamaCpuGate]:
        return build_measured_guarded_deployment(
            Path(manifest_path), manifest_digest=self.manifest_digest,
            manifest_sha256=self.manifest_sha256, maximum_deployment_bytes=self.maximum_deployment_bytes,
            store_path=self.store_path, plan_digest=self.plan_digest,
            model_identity_digest=self.model_identity_digest, policy=self.policy,
            components=components, default_seed=default_seed,
            max_queue_size=max_queue_size, max_batch_size=max_batch_size,
            lease_directory=self.lease_directory,
        )


    def inspect(self, manifest_path: str | Path) -> dict:
        """Check the same independent source/profile pins without activating a provider.

        This performs real reads and local hardware observations only. It
        deliberately accepts no tokenizer, Mongo authority or reviewer.
        Consequently even a passing result cannot qualify protected chat.
        """
        try:
            deployment, source = _resolve_measured_source(
                Path(manifest_path), manifest_digest=self.manifest_digest,
                manifest_sha256=self.manifest_sha256,
                maximum_deployment_bytes=self.maximum_deployment_bytes,
                store_path=self.store_path, plan_digest=self.plan_digest,
                model_identity_digest=self.model_identity_digest, policy=self.policy,
            )
            backend = LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
            backend.assert_identity()
            require(backend.runtime_digest == deployment.executable_sha256,
                    "native runtime differs from pinned deployment")
            gate = MeasuredLlamaCpuGate(backend, source, self.policy)
        except (LocalModelDeploymentError, LlamaCppRuntimeError) as exc:
            raise RuntimePreflightError("deployment source or profile unavailable") from exc
        try:
            try:
                gate()
            except RuntimePreflightError:
                # The gate records its latest denied observation. Never turn
                # a missing observation into a successful source-only check.
                pass
            observation = gate.status()["last"]
        finally:
            gate.close()
        require(type(observation) is dict, "missing measured deployment observation")
        body = {
            "schema": "skeleton.offline.measured-deployment-inspection.v1",
            "manifest_digest": self.manifest_digest, "manifest_sha256": self.manifest_sha256,
            "plan_digest": self.plan_digest, "model_identity_digest": self.model_identity_digest,
            "model_digest": backend.model_digest, "runtime_digest": backend.runtime_digest,
            "execution_profile_digest": backend.execution_profile_digest,
            "model_is_jeeves": backend.model_id == "jeeves",
            "source_bytes": source.plan.expected_total_bytes,
            "observation": observation, "status": observation["status"],
            "protected_authorities": "not_assessed", "provider_activation": "not_performed",
            "transferable_grant": False, "native_qualified": False, "release_qualified": False,
        }
        return {**body, "inspection_digest": digest(body)}
