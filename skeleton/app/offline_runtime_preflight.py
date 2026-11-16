"""Join archived local-model custody, resource probes and placement contracts.

Preflight is advisory. A verified source is not a loaded tensor, an allocated
device, a licensed model, an executable backend, or an inference result.
Only explicit local operator paths are used. No hosted fallback is present.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import time
from typing import Any

from skeleton.ai.model_runtime.device_placement import (
    DeviceDescriptor, ModelRuntimeError, NativeGpuMemoryReceipt,
    plan_device_placement, probe_linux_nvidia_memory,
)
from skeleton.ai.model_runtime.flgb_model_runtime import WeightLoadPlan
from skeleton.ai.model_runtime.offline_inventory import inventory_offline_weights
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore
from skeleton.app.offline_cpu_budget import (
    CpuTopology, MemoryTopology, plan_cpu_workers, probe_cpu_topology,
    probe_memory_topology,
)
from skeleton.app.offline_energy_budget import (
    EnergyPolicy, PowerObservation, plan_energy_workers, probe_power,
)
from skeleton.native.gguf_preflight import inspect_gguf

SCHEMA = "skeleton.offline.runtime-preflight.v1"
MAX_SOURCE_BYTES = 1 << 40
MAX_INVENTORY = 4096
MIB = 1024**2
MAX_SAMPLE_NS = 30 * 10**9


class RuntimePreflightError(ValueError):
    """Invalid source binding, measured evidence or resource contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimePreflightError(message)


def integer(value: Any, minimum: int, maximum: int, name: str) -> int:
    require(type(value) is int and minimum <= value <= maximum, "invalid " + name)
    return value


def identity(value: Any, name: str) -> str:
    require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None,
            "invalid " + name)
    return value


def canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise RuntimePreflightError("invalid canonical receipt") from exc
    require(len(raw) <= 4 * MIB, "runtime receipt exceeds byte limit")
    return raw


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    backend: str = "cpu"
    maximum_source_bytes: int = 128 * 1024**3
    maximum_inventory_entries: int = 64
    verify_gguf_headers: bool = True
    maximum_workers: int = 8
    bytes_per_worker: int = 256 * MIB
    host_reserve_bytes: int = 1024 * MIB
    device_reserve_bytes: int = 512 * MIB
    interactive_cpu_reserve: int = 1
    maximum_tokens: int = 2048
    prefill_quantum: int = 512
    sample_age_ns: int = 5 * 10**9

    def __post_init__(self) -> None:
        require(self.backend in ("cpu", "cuda", "hybrid"), "invalid backend policy")
        require(type(self.verify_gguf_headers) is bool, "invalid GGUF framing flag")
        for name, low, high in (
            ("maximum_source_bytes", 24, MAX_SOURCE_BYTES),
            ("maximum_inventory_entries", 1, MAX_INVENTORY),
            ("maximum_workers", 1, 256),
            ("bytes_per_worker", 1, MAX_SOURCE_BYTES),
            ("host_reserve_bytes", 0, MAX_SOURCE_BYTES),
            ("device_reserve_bytes", 0, MAX_SOURCE_BYTES),
            ("interactive_cpu_reserve", 0, 4096),
            ("maximum_tokens", 1, 65536),
            ("prefill_quantum", 1, 65536),
            ("sample_age_ns", 1, MAX_SAMPLE_NS),
        ):
            integer(getattr(self, name), low, high, name)
        require(self.prefill_quantum <= self.maximum_tokens, "prefill exceeds token ceiling")


@dataclass(frozen=True, slots=True)
class ModelSource:
    plan_digest: str
    model_identity_digest: str
    inventory_digest: str
    plan: WeightLoadPlan
    headers: tuple[dict, ...]

    def __post_init__(self) -> None:
        for key in ("plan_digest", "model_identity_digest", "inventory_digest"):
            identity(getattr(self, key), key)
        require(isinstance(self.plan, WeightLoadPlan)
                and self.plan.digest == self.plan_digest
                and self.plan.model_identity_digest == self.model_identity_digest,
                "selected source plan identity mismatch")
        require(type(self.headers) is tuple and len(self.headers) in (0, len(self.plan.shards)),
                "incomplete GGUF framing set")
        for shard, header in zip(self.plan.shards, self.headers):
            require(type(header) is dict and set(header) == {
                "version", "tensor_count", "metadata_count", "file_size", "sha256"
            }, "invalid GGUF framing receipt")
            require(header["sha256"] == shard.digest and header["file_size"] == shard.bytes,
                    "GGUF receipt does not bind shard identity")
            integer(header["version"], 2, 3, "GGUF version")
            integer(header["tensor_count"], 1, 1_000_000, "tensor count")
            integer(header["metadata_count"], 0, 1_000_000, "metadata count")

    def snapshot(self) -> dict:
        return {"plan_digest": self.plan_digest, "model_identity_digest": self.model_identity_digest,
                "inventory_digest": self.inventory_digest, "weight_bytes": self.plan.expected_total_bytes,
                "shards": [{"index": row.index, "digest": row.digest, "bytes": row.bytes,
                            "source_label_digest": digest(row.source)} for row in self.plan.shards],
                "gguf_headers": [dict(row) for row in self.headers],
                "tensor_validation": "not_assessed", "activation": "not_performed"}


def inspect_source(root: Path, *, plan_digest: str, model_identity_digest: str,
                   policy: RuntimePolicy) -> ModelSource:
    """Read verified inventory, independently pin one plan, optionally inspect all GGUFs."""
    identity(plan_digest, "plan digest")
    identity(model_identity_digest, "model identity")
    require(isinstance(policy, RuntimePolicy), "runtime policy required")
    inventory = inventory_offline_weights(root, max_entries=policy.maximum_inventory_entries,
                                          max_weight_bytes=policy.maximum_source_bytes)
    matches = [row for row in inventory["models"] if row["plan_digest"] == plan_digest]
    require(len(matches) == 1 and matches[0]["model_identity_digest"] == model_identity_digest,
            "requested plan is not in verified inventory under pinned identity")
    store = WeightShardStore(root, maximum_bytes=policy.maximum_source_bytes, read_only=True)
    plan = store.load_plan(plan_digest)
    paths = store.verified_paths(plan_digest)
    require(plan.model_identity_digest == model_identity_digest
            and plan.expected_total_bytes == matches[0]["weight_bytes"]
            and len(paths) == matches[0]["shard_count"], "inventory and selected plan differ")
    headers = ()
    if policy.verify_gguf_headers:
        headers = tuple(asdict(inspect_gguf(path, expected_sha256=shard.digest, max_bytes=shard.bytes))
                        for shard, path in zip(plan.shards, paths))
    return ModelSource(plan_digest, model_identity_digest, inventory["digest"], plan, headers)


@dataclass(frozen=True, slots=True)
class HardwareSample:
    cpu: CpuTopology
    memory: MemoryTopology
    power: PowerObservation
    gpu: NativeGpuMemoryReceipt
    started_ns: int
    finished_ns: int
    origin: str
    scoped_pressure: str | None = None
    scoped_observation_digest: str | None = None

    def __post_init__(self) -> None:
        require(isinstance(self.cpu, CpuTopology) and isinstance(self.memory, MemoryTopology)
                and isinstance(self.power, PowerObservation) and isinstance(self.gpu, NativeGpuMemoryReceipt),
                "canonical hardware observations required")
        integer(self.started_ns, 0, 2**63-1, "sample start")
        integer(self.finished_ns, self.started_ns, 2**63-1, "sample finish")
        require(self.origin in ("local_probe", "fixture"), "invalid sample origin")
        require(self.scoped_pressure in (None, "normal", "recovering", "elevated", "critical"),
                "invalid scoped serving pressure")
        require((self.scoped_pressure is None) == (self.scoped_observation_digest is None),
                "incomplete scoped serving observation")
        if self.scoped_observation_digest is not None:
            identity(self.scoped_observation_digest, "scoped serving observation")
        if self.gpu.status == "measured":
            require(len(self.gpu.devices) <= 32 and len({d.device_id for d in self.gpu.devices}) == len(self.gpu.devices)
                    and sum(d.memory_bytes for d in self.gpu.devices) == self.gpu.measured_free_bytes,
                    "inconsistent native device memory aggregate")
            require(all(d.kind == "cuda" and d.device_id != "host-cpu" for d in self.gpu.devices),
                    "unexpected native device identity")
        if self.origin == "local_probe":
            require(self.gpu.source != "simulated_nvml", "simulated GPU cannot enter live sample")

    def snapshot(self) -> dict:
        return {"cpu": asdict(self.cpu), "memory": asdict(self.memory), "power": asdict(self.power),
                "gpu": self.gpu.snapshot(), "started_ns": self.started_ns,
                "finished_ns": self.finished_ns, "origin": self.origin,
                "scoped_pressure": self.scoped_pressure,
                "scoped_observation_digest": self.scoped_observation_digest}


def intersect_scoped_headroom(memory: MemoryTopology, serving) -> MemoryTopology:
    """Use the lower of host and canonical process-scoped allocation limits.

    Host free bytes alone are insufficient in nested containers or when
    Windows commit is restricted. Missing scoped residency telemetry is
    unavailable, not an unlimited allocation budget.
    """
    from skeleton.ai.runtime.inference.adaptive_serving import ServingResources

    require(isinstance(memory, MemoryTopology) and isinstance(serving, ServingResources),
            "canonical scoped memory evidence required")
    scoped = serving.allocation_headroom_bytes
    available = memory.available_bytes
    if scoped is None or available is None or serving.available_memory_bytes is None:
        available = None
    else:
        available = min(available, scoped)
    return MemoryTopology(memory.total_bytes, available, "intersection-with-serving-headroom")


def sample_hardware() -> HardwareSample:
    # Import lazily to keep fixture-only planning independent of the serving
    # engine and to reuse its existing OS/cgroup/commit telemetry authority.
    from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController
    from skeleton.ai.runtime.inference.local import sample_serving_resources

    started = time.monotonic_ns()
    cpu, memory = probe_cpu_topology(), probe_memory_topology()
    power, gpu = probe_power(), probe_linux_nvidia_memory()
    serving = sample_serving_resources(fresh=True)
    memory = intersect_scoped_headroom(memory, serving)
    finished = time.monotonic_ns()
    pressure = AdaptiveServingController(1)
    pressure.update(serving, now=finished / 1_000_000_000, queued=0)
    return HardwareSample(cpu, memory, power, gpu, started, finished, "local_probe",
                          pressure.level, digest(serving.as_dict()))


def _placement(source: ModelSource, sample: HardwareSample, policy: RuntimePolicy) -> tuple[list, list, str]:
    devices = []
    available = sample.memory.available_bytes
    # Reserve host service RAM up front. GPU and system bytes are never merged
    # into a fictitious single physical address space.
    if policy.backend in ("cpu", "hybrid") and available is not None:
        # Hybrid placement must preserve at least one host worker before
        # choosing residency; later CPU/energy planning can tighten further.
        worker_floor = policy.bytes_per_worker if policy.backend == "hybrid" else 0
        capacity = max(0, available - policy.host_reserve_bytes - worker_floor)
        if capacity:
            devices.append(DeviceDescriptor("host-cpu", "cpu", capacity))
    if policy.backend in ("cuda", "hybrid") and sample.gpu.status == "measured":
        for device in sample.gpu.devices:
            require(device.kind == "cuda", "unexpected native GPU kind")
            remaining = max(0, device.memory_bytes - policy.device_reserve_bytes)
            if device.available and remaining:
                devices.append(DeviceDescriptor(device.device_id, "cuda", remaining))
    # CUDA and hybrid policies require actual/fixture CUDA observations, not
    # silent fallback to a different backend.
    if policy.backend != "cpu" and not any(d.kind == "cuda" for d in devices):
        return [], [asdict(d) for d in devices], "cuda_memory_unavailable"
    if not devices:
        return [], [], "placement_memory_unavailable"
    try:
        placement = plan_device_placement(
            source.plan.shards, devices,
            preferred_kind="cuda" if policy.backend == "hybrid" else None,
        )
    except ModelRuntimeError:
        return [], [asdict(d) for d in devices], "canonical_placement_rejected"
    if policy.backend == "hybrid" and not any(row.device_id != "host-cpu" for row in placement):
        # Presence of a GPU is not evidence that any selected shard fits it.
        return [], [asdict(d) for d in devices], "hybrid_cuda_shard_unavailable"
    return [asdict(row) for row in placement], [asdict(d) for d in devices], "candidate"


def plan_preflight(source: ModelSource, sample: HardwareSample, policy: RuntimePolicy,
                   *, now_ns: int) -> dict:
    """Pure planning against captured evidence, never allocate or load anything."""
    require(isinstance(source, ModelSource) and isinstance(sample, HardwareSample)
            and isinstance(policy, RuntimePolicy), "validated source, sample and policy required")
    integer(now_ns, 0, 2**63-1, "planning timestamp")
    age = now_ns - sample.started_ns
    fresh = 0 <= age <= policy.sample_age_ns and sample.finished_ns <= now_ns
    require(source.plan.expected_total_bytes <= policy.maximum_source_bytes, "source exceeds policy")
    require(not policy.verify_gguf_headers or bool(source.headers), "GGUF framing required")
    placements, devices, placement_status = _placement(source, sample, policy)
    host_weights = sum(row["bytes"] for row in placements if row["device_id"] == "host-cpu")
    # Host worker budget must not double-count memory assigned to CPU weights.
    cpu = plan_cpu_workers(sample.cpu, sample.memory, operator_max_workers=policy.maximum_workers,
                          bytes_per_worker=policy.bytes_per_worker,
                          memory_reserve_bytes=policy.host_reserve_bytes + host_weights,
                          interactive_cpu_reserve=min(policy.interactive_cpu_reserve,
                                                      sample.cpu.logical_visible),
                          thermal_state="normal")
    energy = plan_energy_workers(cpu, sample.power, policy=EnergyPolicy())
    blockers = []
    if not fresh:
        blockers.append("stale_or_future_hardware_sample")
    if sample.scoped_pressure == "critical":
        blockers.append("canonical_scoped_serving_pressure_critical")
    if placement_status != "candidate":
        blockers.append(placement_status)
    if sample.memory.available_bytes is None or not sample.memory.total_bytes:
        blockers.append("host_memory_telemetry_unavailable")
    if not energy.allowed_workers:
        blockers.append("energy_or_worker_budget_zero")
    host_fraction = None
    if sample.memory.total_bytes and sample.memory.available_bytes is not None:
        host_fraction = 1.0 - max(0, sample.memory.available_bytes - host_weights) / sample.memory.total_bytes
    gpu_fraction = None
    gpu_pressure_rows = []
    gpu_pressure_basis = "not_applicable" if policy.backend == "cpu" else "unavailable"
    if policy.backend != "cpu" and sample.gpu.status == "measured" and sample.gpu.measured_total_bytes:
        allocated = {}
        for row in placements:
            device_id = row["device_id"]
            if device_id != "host-cpu":
                allocated[device_id] = allocated.get(device_id, 0) + row["bytes"]
        if sample.gpu.observations:
            # Aggregate headroom can conceal a nearly saturated selected
            # device behind an idle, unrelated GPU. Conversely, saturation
            # on an unused GPU should not throttle a valid packing.
            for observation in sample.gpu.observations:
                weight_bytes = allocated.get(observation.device_id, 0)
                if not weight_bytes:
                    continue
                remaining = observation.free_bytes - weight_bytes
                require(remaining >= policy.device_reserve_bytes,
                        "placement exceeds measured per-device reserve")
                projected = 1.0 - remaining / observation.total_bytes
                gpu_pressure_rows.append({
                    "device_id": observation.device_id,
                    "weight_bytes": weight_bytes,
                    "projected_free_bytes": remaining,
                    "projected_occupancy": projected,
                })
            if gpu_pressure_rows:
                gpu_fraction = max(row["projected_occupancy"] for row in gpu_pressure_rows)
                gpu_pressure_basis = "selected_device_maximum"
        elif sample.origin == "fixture":
            # Legacy pure-planning fixtures lack physical device totals.
            # Never promote aggregate-only evidence into a live GPU grant.
            gpu_weights = sum(allocated.values())
            gpu_fraction = 1.0 - max(0, sample.gpu.measured_free_bytes - gpu_weights) / sample.gpu.measured_total_bytes
            gpu_pressure_basis = "fixture_aggregate_only"
    if policy.backend != "cpu" and gpu_fraction is None:
        blockers.append("gpu_pressure_unavailable")
    fractions = [v for v in (host_fraction, gpu_fraction) if v is not None]
    pressure = max(fractions) if fractions else None
    if pressure is None or not math.isfinite(pressure) or pressure >= 1.0:
        blockers.append("memory_pressure_unavailable_or_exhausted")
    workers = 0 if blockers else energy.allowed_workers
    body = {"schema": SCHEMA, "source": source.snapshot(), "policy": asdict(policy),
            "hardware": sample.snapshot(), "now_ns": now_ns, "fresh": fresh,
            "placement_status": placement_status, "placement": placements, "devices": devices,
            "host_weight_bytes": host_weights, "cpu_plan": asdict(cpu), "energy_plan": asdict(energy),
            "pressure_fraction": pressure, "pressure_basis": "projected_memory_occupancy_not_psi",
            "gpu_pressure_basis": gpu_pressure_basis, "gpu_pressure": gpu_pressure_rows,
            "worker_ceiling": workers, "blockers": blockers,
            "status": "candidate" if workers else "blocked",
            "evidence_origin": sample.origin, "model_activation": "not_performed",
            "native_qualified": False, "release_qualified": False}
    return {**body, "preflight_digest": digest(body)}
