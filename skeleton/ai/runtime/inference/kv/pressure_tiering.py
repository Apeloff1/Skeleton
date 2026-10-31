"""Measured, bounded KV tier migration planning for the canonical local cache.

This is a resource-control plane, not a GPU driver or model authority. It
never reads tensor bytes or fabricates device measurements. The caller supplies
source-labelled, recent OS telemetry and the existing KVStorageAdapter performs
physical movement. Unknown telemetry prevents speculative migration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from .manager import KVCacheManager
from .types import CacheTier, KVResidentPage


def _positive(value: object, name: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError(f"invalid {name}")
    return value


def _digest(body: object) -> str:
    return sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class TierPressurePolicy:
    gpu_high_pct: int = 90
    cpu_high_pct: int = 90
    min_disk_reserve_bytes: int = 256 * 1024 * 1024
    min_cpu_headroom_bytes: int = 64 * 1024 * 1024
    max_moves_per_round: int = 8
    max_sample_age_ns: int = 5_000_000_000
    cooldown_ns: int = 1_000_000_000

    def __post_init__(self) -> None:
        for name in ("gpu_high_pct", "cpu_high_pct"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError(f"invalid {name}")
        for name in ("min_disk_reserve_bytes", "min_cpu_headroom_bytes",
                     "max_moves_per_round", "max_sample_age_ns", "cooldown_ns"):
            _positive(getattr(self, name), name)
        if self.max_moves_per_round > 128:
            raise ValueError("migration batch exceeds safety bound")


@dataclass(frozen=True, slots=True)
class TierPressureSample:
    observed_at_ns: int
    source: str
    gpu_pressure_pct: int | None = None
    cpu_pressure_pct: int | None = None
    cpu_available_bytes: int | None = None
    disk_free_bytes: int | None = None

    def __post_init__(self) -> None:
        _positive(self.observed_at_ns, "observed_at_ns", allow_zero=True)
        if (type(self.source) is not str or not 1 <= len(self.source) <= 128
                or any(ord(c) < 32 or ord(c) == 127 for c in self.source)):
            raise ValueError("source-labelled telemetry required")
        for name in ("gpu_pressure_pct", "cpu_pressure_pct"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or not 0 <= value <= 100):
                raise ValueError(f"invalid {name}")
        for name in ("cpu_available_bytes", "disk_free_bytes"):
            value = getattr(self, name)
            if value is not None:
                _positive(value, name, allow_zero=True)


@dataclass(frozen=True, slots=True)
class TierMove:
    page_key: str
    source: CacheTier
    target: CacheTier
    bytes: int


@dataclass(frozen=True, slots=True)
class TierPlan:
    inventory_digest: str
    sample: TierPressureSample
    moves: tuple[TierMove, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class TierApplyReceipt:
    plan_digest: str
    moved: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    digest: str


class KVPressureTierPlanner:
    """Conservative, hysteretic GPU/CPU/disk demotion with exact-head receipts."""

    def __init__(self, policy: TierPressurePolicy | None = None) -> None:
        if policy is not None and not isinstance(policy, TierPressurePolicy):
            raise ValueError("TierPressurePolicy required")
        self.policy = policy or TierPressurePolicy()
        self._last_migration_ns: int | None = None

    @staticmethod
    def _inventory_digest(pages: tuple[KVResidentPage, ...]) -> str:
        return _digest({
            "schema": "skeleton.ai.kv-tier-inventory.v1",
            "pages": [asdict(page) for page in pages],
        })

    def plan(
        self, manager: KVCacheManager, sample: TierPressureSample, *, now_ns: int,
    ) -> TierPlan:
        if not isinstance(manager, KVCacheManager) or not isinstance(sample, TierPressureSample):
            raise ValueError("canonical KV manager and measured sample required")
        _positive(now_ns, "now_ns", allow_zero=True)
        if not sample.observed_at_ns <= now_ns <= sample.observed_at_ns + self.policy.max_sample_age_ns:
            raise ValueError("stale or future resource telemetry")
        pages = manager.tier_inventory()
        inventory_digest = self._inventory_digest(pages)
        moves: list[TierMove] = []
        gpu_pressure = sample.gpu_pressure_pct
        cpu_pressure = sample.cpu_pressure_pct
        cpu_free = sample.cpu_available_bytes
        disk_free = sample.disk_free_bytes
        cooldown = (self._last_migration_ns is not None
                    and now_ns - self._last_migration_ns < self.policy.cooldown_ns)
        if not cooldown:
            # Oldest first; pinned pages are never moved by this controller.
            candidates = sorted(
                (p for p in pages if p.pin_count == 0),
                key=lambda p: (p.last_access, p.key),
            )
            for page in candidates:
                if len(moves) >= self.policy.max_moves_per_round:
                    break
                target: CacheTier | None = None
                if page.tier is CacheTier.GPU and gpu_pressure is not None and gpu_pressure >= self.policy.gpu_high_pct:
                    if (cpu_pressure is not None and cpu_pressure < self.policy.cpu_high_pct
                            and cpu_free is not None
                            and cpu_free - page.size_bytes >= self.policy.min_cpu_headroom_bytes):
                        target = CacheTier.CPU
                        cpu_free -= page.size_bytes
                    elif (disk_free is not None
                          and disk_free - page.size_bytes >= self.policy.min_disk_reserve_bytes):
                        target = CacheTier.NVME
                        disk_free -= page.size_bytes
                elif (page.tier is CacheTier.CPU and cpu_pressure is not None
                      and cpu_pressure >= self.policy.cpu_high_pct
                      and disk_free is not None
                      and disk_free - page.size_bytes >= self.policy.min_disk_reserve_bytes):
                    target = CacheTier.NVME
                    disk_free -= page.size_bytes
                if target is not None:
                    moves.append(TierMove(page.key, page.tier, target, page.size_bytes))
        body = {
            "schema": "skeleton.ai.kv-pressure-plan.v1",
            "inventory_digest": inventory_digest,
            "sample": asdict(sample),
            "policy": asdict(self.policy),
            "moves": [asdict(move) for move in moves],
        }
        return TierPlan(inventory_digest, sample, tuple(moves), _digest(body))

    def apply(
        self, manager: KVCacheManager, plan: TierPlan, *, now_ns: int,
    ) -> TierApplyReceipt:
        if not isinstance(plan, TierPlan):
            raise ValueError("TierPlan required")
        # Recompute under the same measured inputs. A stale plan, changed pin,
        # or changed resident identity must never be accepted as a migration.
        if self.plan(manager, plan.sample, now_ns=now_ns) != plan:
            raise ValueError("KV pressure plan or inventory changed")
        moved: list[str] = []
        rejected: list[tuple[str, str]] = []
        for move in plan.moves:
            try:
                ok = manager.migrate_if(
                    move.page_key, source=move.source,
                    target=move.target, expected_bytes=move.bytes,
                )
            except Exception as exc:
                rejected.append((move.page_key, type(exc).__name__))
            else:
                if ok:
                    moved.append(move.page_key)
                else:
                    rejected.append((move.page_key, "resident_page_changed"))
        if moved:
            self._last_migration_ns = now_ns
        body = {
            "schema": "skeleton.ai.kv-pressure-apply.v1",
            "plan_digest": plan.digest,
            "moved": moved,
            "rejected": rejected,
        }
        return TierApplyReceipt(plan.digest, tuple(moved), tuple(rejected), _digest(body))


__all__ = [
    "KVPressureTierPlanner", "TierApplyReceipt", "TierMove", "TierPlan",
    "TierPressurePolicy", "TierPressureSample",
]
