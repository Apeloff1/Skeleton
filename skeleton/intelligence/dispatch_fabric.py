"""Topology, migration, preload and pressure proposals for the physical owner.

No device, memory mapping, cache, DMA or process is modified here.
The resource owner must independently establish identities, stop/fence
execution, reserve shared backing, copy, verify and acknowledge publication.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from heapq import heappush, heappop
import json

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier
from .dispatch_cognitive import digest, binding


@dataclass(frozen=True, slots=True)
class FabricLink:
    source: str
    target: str
    generation: int
    latency_us: int
    available_bytes_s: int
    transport: str
    verified: bool

    def __post_init__(self) -> None:
        identifier(self.source)
        identifier(self.target)
        identifier(self.transport)
        if self.source == self.target or type(self.verified) is not bool:
            raise DispatchPolicyError("invalid fabric link")
        bounded_int(self.generation, "generation")
        bounded_int(self.latency_us, "latency")
        bounded_int(self.available_bytes_s, "bandwidth", 1)


@dataclass(frozen=True, slots=True)
class TransferPath:
    endpoints: tuple[str, ...]
    transports: tuple[str, ...]
    generation: int
    conservative_us: int
    bottleneck_bytes_s: int
    path_sha256: str


def transfer_path(source: str, target: str, links: Sequence[FabricLink], *,
                  bytes_to_copy: int, generation: int, allowed_transports: frozenset[str],
                  maximum_hops: int = 8) -> TransferPath | None:
    """Find a minimum serial-copy-time path over verified directed links.

    A link observation is not evidence of direct peer DMA or allocated
    bandwidth. Sum per-hop copy times rather than assume pipeline overlap.
    """
    identifier(source)
    identifier(target)
    bounded_int(bytes_to_copy, "transfer bytes", 1)
    bounded_int(generation, "generation")
    bounded_int(maximum_hops, "hops", 1, 16)
    if source == target or type(allowed_transports) is not frozenset or not 1 <= len(allowed_transports) <= 32:
        raise DispatchPolicyError("invalid topology scope")
    for transport in allowed_transports:
        identifier(transport)
    if len(links) > 16384 or any(not isinstance(link, FabricLink) for link in links):
        raise DispatchPolicyError("invalid topology links")
    keys = [(l.source, l.target, l.transport) for l in links]
    if len(set(keys)) != len(keys):
        raise DispatchPolicyError("duplicate topology observation")
    if any(l.generation != generation for l in links):
        raise DispatchPolicyError("mixed topology generation")
    graph: dict[str, list[FabricLink]] = {}
    for link in links:
        if link.verified and link.transport in allowed_transports:
            graph.setdefault(link.source, []).append(link)
    for rows in graph.values():
        rows.sort(key=lambda l: (l.target, l.transport))
    # Dynamic programming in the (endpoint, hops) graph. Positive edge cost
    # means an optimal path cannot contain a cycle.
    queue = [(0, (source,), (), 0, 10**15)]
    best: dict[tuple[str, int], tuple[int, tuple[str, ...], tuple[str, ...]]] = {}
    while queue:
        cost, path, transports, hops, bottleneck = heappop(queue)
        key = (path[-1], hops)
        rank = (cost, path, transports)
        if key in best and rank >= best[key]:
            continue
        best[key] = rank
        if path[-1] == target:
            return TransferPath(path, transports, generation, cost, bottleneck,
                                binding("transfer-path-v1", generation, bytes_to_copy,
                                        path, transports, cost, bottleneck))
        if hops == maximum_hops:
            continue
        for link in graph.get(path[-1], ()):
            edge_cost = link.latency_us + (bytes_to_copy * 1_000_000 + link.available_bytes_s - 1) // link.available_bytes_s
            heappush(queue, (cost + edge_cost, path + (link.target,),
                            transports + (link.transport,), hops + 1,
                            min(bottleneck, link.available_bytes_s)))
    return None


@dataclass(frozen=True, slots=True)
class MigrationSnapshot:
    task_id: str
    tenant_id: str
    source_device: str
    target_device: str
    source_generation: int
    target_generation: int
    model_sha256: str
    source_abi_sha256: str
    target_abi_sha256: str
    policy_sha256: str
    checkpoint_sha256: str
    stop_receipt_sha256: str
    bytes_to_copy: int
    target_free_bytes: int
    scratch_bytes: int
    remaining_deadline_us: int
    predicted_source_us: int
    predicted_target_us: int
    verified_stop: bool
    target_receipt_verified: bool

    def __post_init__(self) -> None:
        for value in (self.task_id, self.tenant_id, self.source_device, self.target_device):
            identifier(value)
        for value in (self.model_sha256, self.source_abi_sha256, self.target_abi_sha256,
                      self.policy_sha256, self.checkpoint_sha256, self.stop_receipt_sha256):
            digest(value)
        for name in ("source_generation", "target_generation", "target_free_bytes",
                     "scratch_bytes", "remaining_deadline_us"):
            bounded_int(getattr(self, name), name)
        for name in ("bytes_to_copy", "predicted_source_us", "predicted_target_us"):
            bounded_int(getattr(self, name), name, 1)
        if type(self.verified_stop) is not bool or type(self.target_receipt_verified) is not bool:
            raise DispatchPolicyError("invalid migration evidence flags")


@dataclass(frozen=True, slots=True)
class MigrationProposal:
    path: TransferPath
    target_reservation_bytes: int
    estimated_total_us: int
    binding_sha256: str
    required_phases: tuple[str, ...] = ("reserve-target", "copy", "verify-checkpoint",
                                       "publish-target", "ack-source-release")


def propose_migration(snapshot: MigrationSnapshot, links: Sequence[FabricLink], *,
                      topology_generation: int, allowed_transports: frozenset[str],
                      minimum_gain_us: int = 1) -> MigrationProposal | None:
    """Only propose a stopped, source/ABI/target-bound checkpoint transfer.

    The stop flags are trusted inputs, not independently authenticated by this
    function. Source storage stays reserved until verified target publication.
    """
    bounded_int(minimum_gain_us, "gain", 1)
    if not isinstance(snapshot, MigrationSnapshot):
        raise DispatchPolicyError("invalid migration snapshot")
    s = snapshot
    reserve = s.bytes_to_copy + s.scratch_bytes
    if (not s.verified_stop or not s.target_receipt_verified
            or s.source_abi_sha256 != s.target_abi_sha256
            or s.source_device == s.target_device or reserve > s.target_free_bytes):
        return None
    path = transfer_path(s.source_device, s.target_device, links, bytes_to_copy=s.bytes_to_copy,
                         generation=topology_generation, allowed_transports=allowed_transports)
    if path is None:
        return None
    total = path.conservative_us + s.predicted_target_us
    if total > s.remaining_deadline_us or s.predicted_source_us - total < minimum_gain_us:
        return None
    return MigrationProposal(path, reserve, total, binding(
        "migration-v1", s.task_id, s.tenant_id, s.source_device, s.target_device,
        s.source_generation, s.target_generation, s.model_sha256, s.source_abi_sha256,
        s.policy_sha256, s.checkpoint_sha256, s.stop_receipt_sha256, reserve, total, path.path_sha256,
    ))


@dataclass(frozen=True, slots=True)
class PreloadDemand:
    tenant_id: str
    model_sha256: str
    device_id: str
    generation: int
    observed_ms: int
    forecast_receipt_sha256: str
    probability_ppm: int
    expected_requests: int
    avoided_cold_ms: int
    load_ms: int
    bytes_required: int
    authorized: bool

    def __post_init__(self) -> None:
        identifier(self.tenant_id)
        identifier(self.device_id)
        digest(self.model_sha256)
        digest(self.forecast_receipt_sha256)
        for name in ("generation", "observed_ms", "expected_requests"):
            bounded_int(getattr(self, name), name)
        for name in ("avoided_cold_ms", "load_ms", "bytes_required"):
            bounded_int(getattr(self, name), name, 1)
        bounded_int(self.probability_ppm, "probability", 0, 1_000_000)
        if type(self.authorized) is not bool:
            raise DispatchPolicyError("invalid preload authority")


def plan_preloads(demands: Sequence[PreloadDemand], *, tenant_id: str, device_id: str,
                  generation: int, now_ms: int, spare_bytes: int, spare_io_ms: int,
                  max_age_ms: int = 5000, maximum_models: int = 16) -> tuple[PreloadDemand, ...]:
    """Bound speculative preloading using expected savings per reserved byte.

    Values are forecast inputs, not a trained predictor or guaranteed savings.
    Never evict a live model or use another tenant's memory allowance.
    """
    identifier(tenant_id)
    identifier(device_id)
    for name, value in (("generation", generation), ("now", now_ms),
                        ("spare", spare_bytes), ("io", spare_io_ms)):
        bounded_int(value, name)
    bounded_int(max_age_ms, "age", 1, 60_000)
    bounded_int(maximum_models, "models", 1, 64)
    if len(demands) > 4096 or any(not isinstance(d, PreloadDemand) for d in demands):
        raise DispatchPolicyError("invalid preload demands")
    if len({(d.tenant_id, d.device_id, d.model_sha256) for d in demands}) != len(demands):
        raise DispatchPolicyError("duplicate model observation")
    ranked = []
    for d in demands:
        if (not d.authorized or d.tenant_id != tenant_id or d.device_id != device_id
                or d.generation != generation or not 0 <= now_ms - d.observed_ms <= max_age_ms):
            continue
        gain = d.probability_ppm * d.expected_requests * d.avoided_cold_ms - d.load_ms * 1_000_000
        if gain > 0:
            ranked.append((-Fraction(gain, d.bytes_required), d.model_sha256, d))
    selected = []
    for _, _, d in sorted(ranked, key=lambda row: row[:2]):
        if len(selected) == maximum_models:
            break
        if d.bytes_required <= spare_bytes and d.load_ms <= spare_io_ms:
            selected.append(d)
            spare_bytes -= d.bytes_required
            spare_io_ms -= d.load_ms
    return tuple(selected)


@dataclass(frozen=True, slots=True)
class HealthSample:
    timestamp_ms: int
    generation: int
    pressure_ppm: int
    error_ppm: int

    def __post_init__(self) -> None:
        bounded_int(self.timestamp_ms, "time")
        bounded_int(self.generation, "generation")
        bounded_int(self.pressure_ppm, "pressure", 0, 1_000_000)
        bounded_int(self.error_ppm, "errors", 0, 1_000_000)


@dataclass(frozen=True, slots=True)
class PressureDecision:
    state: str
    projected_pressure_ppm: int
    error_ppm: int
    admission_per_mille: int
    cancel_speculation: bool
    request_idle_eviction: bool


def forecast_pressure(samples: Sequence[HealthSample], *, generation: int,
                      horizon_ms: int, previously_throttled: bool = False,
                      high_ppm: int = 850_000, low_ppm: int = 650_000,
                      error_limit_ppm: int = 50_000) -> PressureDecision:
    """Conservative slope projection with a hysteresis and a fail-closed cold start.

    This is a deterministic early warning, not calibrated failure probability.
    Physical owners alone decide whether an idle eviction is safe.
    """
    bounded_int(generation, "generation")
    bounded_int(horizon_ms, "horizon", 1, 60_000)
    bounded_int(high_ppm, "high", 1, 1_000_000)
    bounded_int(low_ppm, "low", 0, high_ppm - 1)
    bounded_int(error_limit_ppm, "error", 1, 1_000_000)
    if type(previously_throttled) is not bool or not 3 <= len(samples) <= 256:
        raise DispatchPolicyError("insufficient or excessive pressure history")
    if any(not isinstance(s, HealthSample) or s.generation != generation for s in samples):
        raise DispatchPolicyError("mixed pressure generation")
    rows = sorted(samples, key=lambda s: s.timestamp_ms)
    if len({s.timestamp_ms for s in rows}) != len(rows):
        raise DispatchPolicyError("duplicate sample time")
    slopes = [Fraction(b.pressure_ppm - a.pressure_ppm, b.timestamp_ms - a.timestamp_ms)
              for a, b in zip(rows, rows[1:])]
    slope = max(Fraction(0), sorted(slopes)[(len(slopes)-1)//2])
    projected = min(1_000_000, rows[-1].pressure_ppm + int(slope * horizon_ms))
    recent = max(row.error_ppm for row in rows[-3:])
    if recent >= error_limit_ppm or projected >= high_ppm:
        return PressureDecision("throttle", projected, recent, 250, True, True)
    if previously_throttled and (projected > low_ppm or recent * 2 >= error_limit_ppm):
        return PressureDecision("recovering", projected, recent, 500, True, False)
    return PressureDecision("normal", projected, recent, 1000, False, False)
