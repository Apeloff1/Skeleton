"""Bounded hardware and inference planning; actual reservations stay with owners."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import re

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier, MAX_CANDIDATES


def _digest(value: str) -> None:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise DispatchPolicyError("invalid source digest")


def _labels(values: frozenset[str], maximum: int = 128) -> None:
    if type(values) is not frozenset or len(values) > maximum:
        raise DispatchPolicyError("invalid capability set")
    for value in values:
        identifier(value)


@dataclass(frozen=True, slots=True)
class BatchIdentity:
    tenant_id: str
    model_sha256: str
    tokenizer_sha256: str
    adapter_sha256: str
    policy_sha256: str
    precision: str
    phase: str

    def __post_init__(self) -> None:
        identifier(self.tenant_id)
        for digest in (self.model_sha256, self.tokenizer_sha256, self.adapter_sha256, self.policy_sha256):
            _digest(digest)
        identifier(self.precision)
        if self.phase not in {"prefill", "decode"}:
            raise DispatchPolicyError("invalid inference phase")


@dataclass(frozen=True, slots=True)
class BatchDemand:
    task_id: str
    identity: BatchIdentity
    arrival_ms: int
    deadline_ms: int
    priority: int
    tokens: int
    memory_bytes: int
    context_tokens: int
    estimated_ms: int
    uncertainty_ms: int = 0

    def __post_init__(self) -> None:
        identifier(self.task_id)
        if not isinstance(self.identity, BatchIdentity):
            raise DispatchPolicyError("invalid batch identity")
        bounded_int(self.arrival_ms, "arrival")
        bounded_int(self.deadline_ms, "deadline", self.arrival_ms)
        bounded_int(self.priority, "priority", 0, 1000)
        for n in ("tokens", "memory_bytes", "context_tokens", "estimated_ms"):
            bounded_int(getattr(self, n), n, 1)
        bounded_int(self.uncertainty_ms, "uncertainty")


@dataclass(frozen=True, slots=True)
class BatchLimits:
    max_items: int
    max_tokens: int
    max_memory_bytes: int
    max_padded_tokens: int
    max_wait_ms: int
    max_service_ms: int

    def __post_init__(self) -> None:
        bounded_int(self.max_items, "items", 1, 1024)
        for n in ("max_tokens", "max_memory_bytes", "max_padded_tokens", "max_service_ms"):
            bounded_int(getattr(self, n), n, 1)
        bounded_int(self.max_wait_ms, "batch wait", 0, 60_000)


@dataclass(frozen=True, slots=True)
class BatchProposal:
    identity: BatchIdentity
    tasks: tuple[str, ...]
    tokens: int
    memory_bytes: int
    padded_tokens: int
    latest_start_ms: int
    service_upper_ms: int
    dispatch_now: bool
    reason: str


@dataclass(frozen=True, slots=True)
class BatchPlan:
    batches: tuple[BatchProposal, ...]
    rejected: tuple[tuple[str, str], ...]


def plan_batches(demands: Sequence[BatchDemand], limits: BatchLimits, *, now_ms: int,
                 protected_priority: int = 10) -> BatchPlan:
    """Conservative service sums; no physical accelerator speedup is presumed."""
    bounded_int(now_ms, "time")
    bounded_int(protected_priority, "protected priority", 0, 1000)
    if not isinstance(limits, BatchLimits) or len(demands) > MAX_CANDIDATES:
        raise DispatchPolicyError("invalid batch observation")
    if any(not isinstance(d, BatchDemand) for d in demands):
        raise DispatchPolicyError("invalid batch demand")
    if len({d.task_id for d in demands}) != len(demands):
        raise DispatchPolicyError("duplicate batch task")
    groups: dict[tuple[BatchIdentity, bool], list[BatchDemand]] = {}
    rejected: list[tuple[str, str]] = []
    for d in demands:
        if d.arrival_ms > now_ms:
            raise DispatchPolicyError("future arrival")
        if d.tokens > limits.max_tokens or d.memory_bytes > limits.max_memory_bytes or d.context_tokens > limits.max_padded_tokens:
            rejected.append((d.task_id, "oversize"))
            continue
        service = d.estimated_ms + d.uncertainty_ms
        if service > limits.max_service_ms or now_ms + service > d.deadline_ms:
            rejected.append((d.task_id, "deadline_or_service_budget"))
            continue
        groups.setdefault((d.identity, d.priority <= protected_priority), []).append(d)

    proposals: list[tuple[tuple, BatchProposal]] = []

    def publish(rows: list[BatchDemand], full: bool) -> None:
        if not rows:
            return
        service = sum(d.estimated_ms + d.uncertainty_ms for d in rows)
        latest = min(min(d.arrival_ms + limits.max_wait_ms for d in rows),
                     min(d.deadline_ms for d in rows) - service)
        protected = rows[0].priority <= protected_priority
        launch = protected or full or now_ms >= latest
        reason = "protected" if protected else "capacity" if full else "deadline_or_age" if launch else "coalesce"
        proposal = BatchProposal(
            rows[0].identity, tuple(d.task_id for d in rows), sum(d.tokens for d in rows),
            sum(d.memory_bytes for d in rows),
            len(rows) * max(d.context_tokens for d in rows), latest, service, launch, reason,
        )
        proposals.append(((not protected, not launch, latest, min(d.priority for d in rows),
                           proposal.tasks), proposal))

    for rows in groups.values():
        ordered = sorted(rows, key=lambda d: (d.deadline_ms, d.priority, d.arrival_ms, d.task_id))
        batch: list[BatchDemand] = []
        tokens = memory = service = longest = 0
        earliest_deadline = 10**16
        for d in ordered:
            size = len(batch) + 1
            next_service = service + d.estimated_ms + d.uncertainty_ms
            next_deadline = min(earliest_deadline, d.deadline_ms)
            if batch and (
                size > limits.max_items or tokens + d.tokens > limits.max_tokens
                or memory + d.memory_bytes > limits.max_memory_bytes
                or size * max(longest, d.context_tokens) > limits.max_padded_tokens
                or next_service > limits.max_service_ms or now_ms + next_service > next_deadline
            ):
                publish(batch, True)
                batch = []
                tokens = memory = service = longest = 0
                earliest_deadline = 10**16
            batch.append(d)
            tokens += d.tokens
            memory += d.memory_bytes
            service += d.estimated_ms + d.uncertainty_ms
            longest = max(longest, d.context_tokens)
            earliest_deadline = min(earliest_deadline, d.deadline_ms)
        publish(batch, len(batch) == limits.max_items or tokens == limits.max_tokens
                or memory == limits.max_memory_bytes)
    return BatchPlan(tuple(p for _, p in sorted(proposals, key=lambda pair: pair[0])),
                     tuple(sorted(rejected)))


@dataclass(frozen=True, slots=True)
class DeviceObservation:
    node_id: str
    device_id: str
    numa_id: str
    accelerator: str
    capabilities: frozenset[str]
    generation: int
    observed_ms: int
    free_ram_bytes: int
    free_device_bytes: int
    free_unified_bytes: int
    free_io_bytes_s: int
    memory_bw_bytes_s: int
    free_compute_milli: int
    power_mw: int
    thermal_millic: int
    cached_models: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for value in (self.node_id, self.device_id, self.numa_id, self.accelerator):
            identifier(value)
        _labels(self.capabilities)
        _labels(self.cached_models)
        for digest in self.cached_models:
            _digest(digest)
        for n in ("generation", "observed_ms", "free_ram_bytes", "free_device_bytes",
                  "free_unified_bytes", "free_io_bytes_s", "memory_bw_bytes_s",
                  "free_compute_milli", "power_mw"):
            bounded_int(getattr(self, n), n)
        bounded_int(self.thermal_millic, "temperature", -50_000, 200_000)


@dataclass(frozen=True, slots=True)
class DeviceDemand:
    task_id: str
    model_sha256: str
    accelerators: frozenset[str]
    required: frozenset[str]
    ram_bytes: int
    device_bytes: int
    unified_bytes: int
    io_bytes_s: int
    memory_bw_bytes_s: int
    compute_milli: int
    max_power_mw: int
    max_thermal_millic: int
    preferred_numa: str | None = None
    estimated_ms: int = 1

    def __post_init__(self) -> None:
        identifier(self.task_id)
        _digest(self.model_sha256)
        _labels(self.accelerators)
        _labels(self.required)
        if not self.accelerators:
            raise DispatchPolicyError("explicit accelerator eligibility required")
        for n in ("ram_bytes", "device_bytes", "unified_bytes", "io_bytes_s",
                  "memory_bw_bytes_s", "compute_milli", "max_power_mw"):
            bounded_int(getattr(self, n), n)
        bounded_int(self.max_thermal_millic, "thermal cap", 0, 200_000)
        bounded_int(self.estimated_ms, "duration", 1)
        if self.preferred_numa is not None:
            identifier(self.preferred_numa)
        if not any((self.ram_bytes, self.device_bytes, self.unified_bytes,
                    self.io_bytes_s, self.compute_milli, self.memory_bw_bytes_s)):
            raise DispatchPolicyError("empty device demand")


@dataclass(frozen=True, slots=True)
class DeviceProposal:
    node_id: str
    device_id: str
    generation: int
    observed_ms: int
    model_cached: bool
    numa_local: bool
    energy_estimate_mj: int
    bottleneck_share: Fraction


def rank_devices(demand: DeviceDemand, devices: Sequence[DeviceObservation], *, now_ms: int,
                 max_age_ms: int = 5000, reserve_per_mille: int = 100) -> tuple[DeviceProposal, ...]:
    """Owner must establish actual shared backing, then revalidate on reservation."""
    bounded_int(now_ms, "time")
    bounded_int(max_age_ms, "max age", 1, 60_000)
    bounded_int(reserve_per_mille, "reserve", 0, 999)
    if not isinstance(demand, DeviceDemand) or len(devices) > MAX_CANDIDATES:
        raise DispatchPolicyError("invalid placement input")
    if any(not isinstance(d, DeviceObservation) for d in devices):
        raise DispatchPolicyError("invalid device")
    if len({(d.node_id, d.device_id) for d in devices}) != len(devices):
        raise DispatchPolicyError("duplicate device")
    ranks = []
    for d in devices:
        if (d.accelerator not in demand.accelerators or not demand.required <= d.capabilities
                or not 0 <= now_ms - d.observed_ms <= max_age_ms
                or d.thermal_millic > demand.max_thermal_millic
                or d.power_mw > demand.max_power_mw):
            continue
        pairs = ((demand.ram_bytes, d.free_ram_bytes),
                 (demand.device_bytes, d.free_device_bytes),
                 (demand.unified_bytes, d.free_unified_bytes),
                 (demand.io_bytes_s, d.free_io_bytes_s),
                 (demand.memory_bw_bytes_s, d.memory_bw_bytes_s),
                 (demand.compute_milli, d.free_compute_milli))
        capacities = [(need, free * (1000 - reserve_per_mille) // 1000) for need, free in pairs]
        if any(need > available for need, available in capacities):
            continue
        share = max((Fraction(need, available) for need, available in capacities if need), default=Fraction(0))
        cache = demand.model_sha256 in d.cached_models
        local = demand.preferred_numa is None or demand.preferred_numa == d.numa_id
        energy = (d.power_mw * demand.estimated_ms + 999) // 1000
        result = DeviceProposal(d.node_id, d.device_id, d.generation, d.observed_ms, cache, local, energy, share)
        ranks.append(((not cache, not local, share, energy, d.thermal_millic, d.node_id, d.device_id), result))
    return tuple(result for _, result in sorted(ranks, key=lambda row: row[0]))


@dataclass(frozen=True, slots=True)
class CapabilityMiss:
    tenant_id: str
    requirements: frozenset[str]
    observed_generation: int
    expires_ms: int

    def __post_init__(self) -> None:
        identifier(self.tenant_id)
        _labels(self.requirements)
        bounded_int(self.observed_generation, "generation")
        bounded_int(self.expires_ms, "expires")


def should_requeue(miss: CapabilityMiss, *, tenant_id: str, requirements: frozenset[str],
                   now_ms: int, generation: int, changed_capabilities: frozenset[str],
                   capacity_changed: bool = False) -> bool:
    """Invalidate exact tenant-scoped capability misses on relevant changes."""
    identifier(tenant_id)
    _labels(requirements)
    _labels(changed_capabilities)
    bounded_int(now_ms, "time")
    bounded_int(generation, "generation")
    if not isinstance(miss, CapabilityMiss) or type(capacity_changed) is not bool:
        raise DispatchPolicyError("invalid capability observation")
    if miss.tenant_id != tenant_id or miss.requirements != requirements:
        return True
    if generation < miss.observed_generation:
        raise DispatchPolicyError("stale capability generation")
    return now_ms >= miss.expires_ms or (generation > miss.observed_generation and (
        capacity_changed or bool(changed_capabilities & requirements)
    ))


def two_choice_indices(identity: str, generation: int, population: int) -> tuple[int, ...]:
    """Predictably sample two distinct indices from a prefiltered owner list."""
    identifier(identity)
    bounded_int(generation, "generation")
    bounded_int(population, "population", 1, 10_000_000)
    material = sha256(f"{identity}:{generation}".encode()).digest()
    first = int.from_bytes(material[:8], "big") % population
    if population == 1:
        return (first,)
    second = int.from_bytes(material[8:16], "big") % (population - 1)
    if second >= first:
        second += 1
    return first, second
