"""Pure autoscaling recommendations for swarm worker fleets."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from fractions import Fraction
from hashlib import sha256
import json
from contextlib import nullcontext
from collections.abc import Callable

from skeleton.automation.agents.swarm_runtime import SwarmRuntime


@dataclass(frozen=True, slots=True)
class ScaleRecommendation:
    current_slots: int
    desired_slots: int
    delta: int
    queued: int
    reason: str


@dataclass(frozen=True, slots=True)
class AutoscalePolicy:
    target_tasks_per_slot: float = 2.0
    min_slots: int = 1
    max_slots: int = 10_000

    def __post_init__(self) -> None:
        if isinstance(self.target_tasks_per_slot, bool) or not isfinite(self.target_tasks_per_slot) or self.target_tasks_per_slot <= 0:
            raise ValueError("target_tasks_per_slot must be positive")
        if type(self.min_slots) is not int or type(self.max_slots) is not int or self.min_slots < 0 or self.max_slots < self.min_slots:
            raise ValueError("invalid slot bounds")

    def recommend(self, runtime: SwarmRuntime) -> ScaleRecommendation:
        lock = getattr(runtime, "_lock", None)
        with lock if lock is not None else nullcontext():
            snap = runtime.snapshot()
            occupied = snap.leased + sum(t.effect_uncertain for t in runtime.tasks())
            current = snap.available_slots + occupied
            desired = occupied + ceil(snap.queued / self.target_tasks_per_slot)
            desired = max(occupied, min(self.max_slots, max(self.min_slots, desired)))
        delta = desired - current
        reason = "steady"
        if delta > 0:
            reason = "queue demand exceeds target capacity"
        elif delta < 0:
            reason = "capacity exceeds target demand"
        return ScaleRecommendation(current, desired, delta, snap.queued, reason)


@dataclass(frozen=True, slots=True)
class ScaleTelemetry:
    generation: int
    observed_ms: int
    last_demand_ms: int
    last_change_ms: int
    arrivals_per_minute: int
    completions_per_slot_minute: int
    backlog: int
    ready_slots: int
    occupied_slots: int
    warming_slots: int = 0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 10**15:
                raise ValueError("invalid scale telemetry: " + name)
        if self.occupied_slots > self.ready_slots:
            raise ValueError("occupied capacity exceeds ready capacity")
        if max(self.last_change_ms, self.last_demand_ms) > self.observed_ms:
            raise ValueError("future telemetry history")


@dataclass(frozen=True, slots=True)
class ElasticPolicy:
    min_slots: int = 0
    max_slots: int = 10000
    drain_target_ms: int = 60000
    max_age_ms: int = 5000
    warm_retention_ms: int = 300000
    down_cooldown_ms: int = 60000
    maximum_step: int = 64
    zero_ready_verified: bool = False

    def __post_init__(self) -> None:
        for name in ("min_slots", "max_slots", "drain_target_ms", "max_age_ms",
                     "warm_retention_ms", "down_cooldown_ms", "maximum_step"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 10**12:
                raise ValueError("invalid elastic policy: " + name)
        if (self.max_slots < self.min_slots or not self.max_slots or not self.drain_target_ms
                or not self.max_age_ms or not self.maximum_step or type(self.zero_ready_verified) is not bool):
            raise ValueError("invalid elastic limits")

    def recommend(self, telemetry: ScaleTelemetry, *, now_ms: int, generation: int) -> ScaleRecommendation:
        if not isinstance(telemetry, ScaleTelemetry) or type(now_ms) is not int or type(generation) is not int:
            raise ValueError("invalid scaler observation")
        current = telemetry.ready_slots + telemetry.warming_slots
        def result(desired: int, reason: str) -> ScaleRecommendation:
            return ScaleRecommendation(current, desired, desired-current, telemetry.backlog, reason)
        if generation != telemetry.generation or not 0 <= now_ms - telemetry.observed_ms <= self.max_age_ms:
            return result(current, "hold stale or mismatched telemetry")
        occupied = telemetry.occupied_slots
        # A fresh zero rate is not infinite service capacity. Unknown service
        # rate forbids demand-based downscaling and uses bounded upscaling.
        if not telemetry.completions_per_slot_minute:
            if telemetry.backlog or telemetry.arrivals_per_minute:
                return result(max(current, min(self.max_slots, current+self.maximum_step)), "bounded cold-start probe")
            return result(current, "hold unknown service rate")
        drain_rate = Fraction(telemetry.backlog * 60000, self.drain_target_ms)
        needed = ceil((telemetry.arrivals_per_minute + drain_rate) / telemetry.completions_per_slot_minute)
        desired = max(occupied, self.min_slots, min(self.max_slots, needed))
        if telemetry.backlog or telemetry.arrivals_per_minute:
            desired = max(occupied, 1, desired)
        if desired < current:
            if now_ms - telemetry.last_change_ms < self.down_cooldown_ms:
                return result(current, "hold scale-down cooldown")
            if telemetry.warming_slots:
                return result(current, "hold pending activation")
            if desired == 0 and (not self.zero_ready_verified
                                 or now_ms - telemetry.last_demand_ms < self.warm_retention_ms):
                desired = 1
            desired = max(occupied, desired, current-self.maximum_step)
        elif desired > current:
            desired = min(desired, current+self.maximum_step)
        return result(desired, "service-rate demand" if desired != current else "steady")


@dataclass(frozen=True, slots=True)
class IdleRetirement:
    worker_id: str
    capacity: int
    last_seen: float
    generation_sha256: str


def _retirement_identity(worker) -> str:
    # Bind registration epoch using the existing runtime worker object
    # generation below; never accept a reused textual worker id alone.
    return sha256(json.dumps([worker.id, worker.capacity, worker.last_seen,
                              sorted(worker.capabilities), worker.accepted,
                              worker.completed, worker.failed, worker.heartbeats,
                              worker.registration_token],
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def propose_idle_retirements(runtime: SwarmRuntime, *, desired_slots: int,
                             idle_seconds: float, maximum_workers: int = 64,
                             protected: frozenset[str] = frozenset()) -> tuple[IdleRetirement, ...]:
    """Advisory root retirement; never remove a worker needed by queued work."""
    if not runtime.fenced or getattr(runtime, "_lock", None) is None:
        raise ValueError("retirement requires hardened fenced runtime")
    if (type(desired_slots) is not int or desired_slots < 0 or type(maximum_workers) is not int
            or not 1 <= maximum_workers <= 1024 or isinstance(idle_seconds, bool)
            or not isfinite(idle_seconds) or idle_seconds <= 0 or type(protected) is not frozenset):
        raise ValueError("invalid retirement policy")
    with runtime._lock:
        snapshot = runtime.snapshot()
        if snapshot.queued:
            return ()
        occupied = snapshot.leased + sum(t.effect_uncertain for t in runtime.tasks())
        excess = snapshot.available_slots + occupied - max(occupied, desired_slots)
        now = runtime._clock()
        result = []
        for worker in sorted(runtime.workers(), key=lambda w: (w.last_seen, w.id)):
            if len(result) >= maximum_workers:
                break
            if (worker.id in protected or worker.parent_id is not None or worker.delegated_capacity
                    or worker.active or worker.capacity > excess or now - worker.last_seen < idle_seconds):
                continue
            result.append(IdleRetirement(worker.id, worker.capacity, worker.last_seen,
                                         _retirement_identity(worker)))
            excess -= worker.capacity
        return tuple(result)


def retire_idle_verified(runtime: SwarmRuntime, proposal: IdleRetirement, *,
                         verify_stop: Callable[[str, str, str], bool],
                         stop_receipt_sha256: str, desired_slots: int, idle_seconds: float,
                         protected: frozenset[str] = frozenset()) -> bool:
    """Trusted host removes an already stopped idle worker after exact revalidation.

    The verifier must authenticate the external stop evidence, including the
    registration identity. Merely presenting a digest does not stop a process.
    """
    if not isinstance(proposal, IdleRetirement) or not callable(verify_stop):
        raise ValueError("invalid retirement request")
    if (type(stop_receipt_sha256) is not str or len(stop_receipt_sha256) != 64
            or any(c not in "0123456789abcdef" for c in stop_receipt_sha256)):
        raise ValueError("invalid stop receipt")
    if verify_stop(proposal.worker_id, proposal.generation_sha256, stop_receipt_sha256) is not True:
        return False
    if not runtime.fenced or getattr(runtime, "_lock", None) is None:
        raise ValueError("retirement requires hardened fenced runtime")
    with runtime._lock:
        eligible = propose_idle_retirements(runtime, desired_slots=desired_slots,
                                            idle_seconds=idle_seconds, maximum_workers=1024,
                                            protected=protected)
        if proposal not in eligible:
            return False
        runtime.unregister_worker(proposal.worker_id, requeue=False)
        return runtime.worker(proposal.worker_id) is None


@dataclass(frozen=True, slots=True)
class WorkerMemoryObservation:
    worker_id: str
    generation_sha256: str
    observed_seconds: float
    reclaimable_bytes: int
    reload_ms: int

    def __post_init__(self) -> None:
        if (type(self.worker_id) is not str or not self.worker_id
                or type(self.generation_sha256) is not str or len(self.generation_sha256)!=64
                or any(c not in "0123456789abcdef" for c in self.generation_sha256)):
            raise ValueError("invalid worker memory identity")
        if (isinstance(self.observed_seconds,bool) or not isfinite(self.observed_seconds)
                or type(self.reclaimable_bytes) is not int or not 0 <= self.reclaimable_bytes <= 10**15
                or type(self.reload_ms) is not int or not 0 <= self.reload_ms <= 10**12):
            raise ValueError("invalid memory observation")


def propose_memory_passivation(runtime: SwarmRuntime, observations: tuple[WorkerMemoryObservation,...],
                                *, reclaim_bytes: int, desired_slots: int, idle_seconds: float,
                                max_age_seconds: float = 5.0, maximum_workers: int = 64,
                                protected: frozenset[str] = frozenset()) -> tuple[IdleRetirement,...]:
    """Prefer fresh generation-bound reclaimable bytes per reload cost.

    Observed reclaimable bytes must already exclude shared memory and pinned
    descendants. A proposal neither evicts memory nor authorizes physical stop.
    Final stop/removal must use the existing verified retirement boundary.
    """
    if (type(reclaim_bytes) is not int or not 1 <= reclaim_bytes <= 10**15
            or isinstance(max_age_seconds,bool) or not isfinite(max_age_seconds) or max_age_seconds<=0
            or type(maximum_workers) is not int or not 1<=maximum_workers<=1024
            or len(observations)>4096 or any(not isinstance(o,WorkerMemoryObservation) for o in observations)
            or len({o.worker_id for o in observations})!=len(observations)):
        raise ValueError("invalid memory passivation observations")
    if not runtime.fenced or getattr(runtime,"_lock",None) is None:
        raise ValueError("passivation requires hardened fenced runtime")
    with runtime._lock:
        snapshot=runtime.snapshot()
        if snapshot.queued:
            return ()
        # Enumerate all idle eligible roots without over-selecting capacity;
        # perform the memory-prioritized selection against the same slot floor.
        occupied=snapshot.leased+sum(t.effect_uncertain for t in runtime.tasks())
        spare=snapshot.available_slots+occupied-max(occupied,desired_slots)
        now=runtime._clock()
        ranked=[]
        if type(desired_slots) is not int or desired_slots<0 or isinstance(idle_seconds,bool) or not isfinite(idle_seconds) or idle_seconds<=0:
            raise ValueError("invalid passivation floor")
        for o in observations:
            worker=runtime.worker(o.worker_id)
            if (worker is None or worker.id in protected or worker.parent_id is not None
                    or worker.delegated_capacity or worker.active or not o.reclaimable_bytes
                    or now-worker.last_seen<idle_seconds or not 0<=now-o.observed_seconds<=max_age_seconds
                    or _retirement_identity(worker)!=o.generation_sha256):
                continue
            ranked.append((-Fraction(o.reclaimable_bytes,max(1,o.reload_ms)),worker.id,o,worker))
        result=[]
        reclaimed=0
        for _,_,o,worker in sorted(ranked,key=lambda row:row[:2]):
            if len(result)>=maximum_workers or reclaimed>=reclaim_bytes:
                break
            if worker.capacity>spare:
                continue
            result.append(IdleRetirement(worker.id,worker.capacity,worker.last_seen,o.generation_sha256))
            spare-=worker.capacity
            reclaimed+=o.reclaimable_bytes
        return tuple(result)
