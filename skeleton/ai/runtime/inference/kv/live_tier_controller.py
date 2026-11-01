"""CPU/disk OS-backed pressure sampling for canonical KV page tiering.

No GPU telemetry is inferred from system RAM, no GPU transfer is claimed.
The canonical KVStorageAdapter owns physical page migration and must
independently enforce backend memory and filesystem quotas.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic_ns
from typing import Callable

from skeleton.app.offline_resources import LocalResourceSnapshot, probe_local_resources
from .manager import KVCacheManager
from .pressure_tiering import (
    KVPressureTierPlanner, TierApplyReceipt, TierMove, TierPlan,
    TierPressurePolicy, TierPressureSample,
)
from .types import CacheTier


class KVPressureDeferred(RuntimeError):
    """No tier movement occurred; re-sample real OS resources."""


@dataclass(frozen=True, slots=True)
class KVLiveObservation:
    """Conservative OS evidence; unknown GPU capacity stays unknown."""

    sample: TierPressureSample
    disk_reserve_bytes: int
    gpu_device_qualified: bool = False


class KVLiveTierController:
    """Bounded CPU->disk migration with a second fresh resource check.

    This is a local process controller, not a cross-process disk reservation.
    Simulated probes are allowed ONLY for deterministic tests, and are
    source-labelled simulated. A trusted application must use the default
    canonical OS probe and real backend storage adapter.
    """

    def __init__(
        self, manager: KVCacheManager, *,
        storage_path: str, policy: TierPressurePolicy | None = None,
        probe: Callable[[str], LocalResourceSnapshot] | None = None,
        clock: Callable[[], int] | None = None,
        simulated: bool = False,
    ) -> None:
        if not isinstance(manager, KVCacheManager):
            raise ValueError("canonical KV cache manager required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected disk volume required")
        if type(simulated) is not bool:
            raise ValueError("explicit simulation flag required")
        if (probe is not None or clock is not None) and not simulated:
            raise ValueError("injected telemetry must be labelled simulated")
        self._manager = manager
        self._planner = KVPressureTierPlanner(policy)
        self._probe = probe_local_resources if probe is None else probe
        self._clock = monotonic_ns if clock is None else clock
        self._storage_path = storage_path
        self._simulated = simulated
        self._lock = RLock()
        # A single controller must never accept an older clock sample after
        # observing a newer one, including across separate planning rounds.
        self._last_observed_ns: int | None = None

    def _sample(self) -> KVLiveObservation:
        try:
            host = self._probe(self._storage_path)
            now = self._clock()
        except Exception as exc:
            # Probe adapters may raise TypeError, OverflowError or even
            # StopIteration on exhausted test/driver samples. Never let
            # unexpected telemetry authorize physical migration.
            raise KVPressureDeferred("OS resource observation unavailable") from exc
        if not isinstance(host, LocalResourceSnapshot):
            raise KVPressureDeferred("canonical resource snapshot required")
        if type(now) is not int or now < 0:
            raise KVPressureDeferred("invalid monotonic observation clock")
        if self._last_observed_ns is not None and now < self._last_observed_ns:
            raise KVPressureDeferred("monotonic observation clock regressed")
        self._last_observed_ns = now
        # Memory pressure is a conservative MAX across physical RAM usage,
        # kernel memory pressure and swap occupancy. Never count swap as RAM.
        physical_used = 100 - (host.available_ram_bytes * 100 // host.total_ram_bytes)
        kernel_pressure = int(host.memory_pressure_ratio * 100)
        swap_used = (
            100 - host.free_swap_bytes * 100 // host.total_swap_bytes
            if host.total_swap_bytes else 0
        )
        pressure = min(100, max(0, physical_used, kernel_pressure, swap_used))
        sample = TierPressureSample(
            observed_at_ns=now,
            source="simulated_cpu_disk" if self._simulated else "os_cpu_disk",
            gpu_pressure_pct=None,
            cpu_pressure_pct=pressure,
            cpu_available_bytes=host.available_ram_bytes,
            disk_free_bytes=host.free_disk_bytes,
        )
        return KVLiveObservation(
            sample=sample,
            disk_reserve_bytes=self._planner.policy.min_disk_reserve_bytes,
        )

    def plan_live(self) -> tuple[TierPlan, KVLiveObservation]:
        with self._lock:
            observation = self._sample()
            plan = self._planner.plan(
                self._manager, observation.sample,
                now_ns=observation.sample.observed_at_ns,
            )
            return plan, observation

    def apply_live(self, plan: TierPlan) -> TierApplyReceipt:
        """Re-probe each physical page move, stopping on unknown outcomes.

        This is not a cross-process disk reservation. The backend must still
        enforce quotas atomically; the journal retains RUNNING on a partial
        or ambiguous migration. Never infer GPU residency from host RAM.
        """
        if not isinstance(plan, TierPlan):
            raise ValueError("canonical tier plan required")
        with self._lock:
            old = plan.sample
            previous_ns = old.observed_at_ns
            disk_moved = 0

            def check(fresh: TierPressureSample, *, remaining_disk: int) -> None:
                nonlocal previous_ns
                if (
                    fresh.source != old.source
                    or fresh.observed_at_ns < previous_ns
                    or fresh.observed_at_ns - old.observed_at_ns >
                        self._planner.policy.max_sample_age_ns
                    or old.gpu_pressure_pct is not None
                    or fresh.gpu_pressure_pct is not None
                    or old.cpu_available_bytes is None
                    or fresh.cpu_available_bytes is None
                    or old.disk_free_bytes is None
                    or fresh.disk_free_bytes is None
                    or old.cpu_pressure_pct is None
                    or fresh.cpu_pressure_pct is None
                    or fresh.cpu_pressure_pct > old.cpu_pressure_pct
                    or fresh.cpu_available_bytes < old.cpu_available_bytes
                    # Account only for our own already moved NVME bytes;
                    # any additional concurrent disk loss is a hard HOLD.
                    or fresh.disk_free_bytes + disk_moved < old.disk_free_bytes
                    or fresh.disk_free_bytes - remaining_disk <
                        self._planner.policy.min_disk_reserve_bytes
                ):
                    raise KVPressureDeferred("stale or worsening OS headroom")
                previous_ns = fresh.observed_at_ns

            remaining = sum(
                move.bytes for move in plan.moves
                if move.target is CacheTier.NVME
            )
            check(self._sample().sample, remaining_disk=remaining)

            def before_move(move: TierMove, index: int) -> None:
                nonlocal disk_moved
                # Re-check after the prior adapter call and before the next.
                # A failed adapter aborts the loop in the canonical planner.
                pending = sum(
                    item.bytes for item in plan.moves[index:]
                    if item.target is CacheTier.NVME
                )
                check(self._sample().sample, remaining_disk=pending)
                if move.target is CacheTier.NVME:
                    disk_moved += move.bytes

            # The canonical manager independently rechecks page identity,
            # pins, size and storage adapter success under its KV lock.
            return self._planner.apply(
                self._manager, plan, now_ns=previous_ns,
                before_move=before_move,
            )
