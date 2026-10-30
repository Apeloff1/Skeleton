"""Cross-worker, in-process Apple unified-memory GPU residency reservations.

This cooperative ledger tracks reservations for local llama.cpp child process
lifetimes. It prevents multiple *Skeleton-owned* local workers from consuming
the same physical/Metal headroom twice. It is NOT a cross-process OS quota or
a Metal allocation guarantee; unrelated applications remain unaccounted for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Callable
import secrets

from .offline_resources import LocalResourcePressure


@dataclass
class UnifiedMemoryLeaseBook:
    """Conservatively coordinate overlapping native GPU workers."""

    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _claims: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def reserve(self, bytes_needed: int, capacity: int) -> Callable[[], None]:
        if (type(bytes_needed) is not int or bytes_needed <= 0
                or type(capacity) is not int or capacity <= 0):
            raise LocalResourcePressure("invalid unified-memory lease admission")
        with self._lock:
            total = sum(self._claims.values())
            if bytes_needed > capacity or total > capacity - bytes_needed:
                raise LocalResourcePressure(
                    "concurrent local Metal workers exceed observed unified-memory "
                    "capacity; wait for a worker to finish or reduce GPU layers"
                )
            token = secrets.token_hex(24)
            self._claims[token] = bytes_needed
        def release() -> None:
            # Idempotent even when both subprocess-failure and shutdown
            # cleanup paths attempt release; never yield duplicate budget.
            with self._lock:
                self._claims.pop(token, None)
        return release

    def usage(self) -> tuple[int, int]:
        with self._lock:
            return len(self._claims), sum(self._claims.values())


GLOBAL_METAL_LEASE_BOOK = UnifiedMemoryLeaseBook()


def reserve_apple_llama_runtime(model: object) -> Callable[[], None]:
    """Return an idempotent release callback for one pinned native process.

    All CPU KV, model weights and native scratch are accounted against
    physical RAM. The dynamic model/Metal probes and existing preflight
    remain the primary admission authority.
    """
    from .offline_metal_runtime import _apple_silicon
    from .offline_resources import probe_local_resources
    from .offline_resource_fabric import probe_gpu_resources

    if not _apple_silicon():
        return lambda: None
    config = model.config
    layers = config.gpu_layers
    if not layers:
        return lambda: None
    geometry = model.serving_metadata
    if not geometry.block_count or not geometry.kv_bytes_per_token_upper_bound:
        raise LocalResourcePressure("unverified native KV/layer geometry")
    snapshot = probe_local_resources(model.model_artifact.path)
    apple = next((
        device for device in probe_gpu_resources()
        if device.vendor == "apple"
        and device.shared_with_system_ram
        and device.recommended_working_set_bytes is not None
        and device.current_allocated_bytes is not None
    ), None)
    if apple is None:
        raise LocalResourcePressure("Metal unified-memory telemetry unavailable")
    reserved_kv = (
        (config.kv_bytes_per_token
         or geometry.kv_bytes_per_token_upper_bound)
        * (config.context_size or 0)
    )
    offloaded_weight = (
        (model.model_artifact.size_bytes * 2 * layers
         + geometry.block_count - 1) // geometry.block_count
    )
    required = offloaded_weight + config.runtime_scratch_bytes + reserved_kv
    capacity = min(
        int(snapshot.available_ram_bytes * 0.55),
        int(max(0, apple.recommended_working_set_bytes
                - apple.current_allocated_bytes) * 0.70),
    )
    return GLOBAL_METAL_LEASE_BOOK.reserve(required, capacity)


__all__ = [
    "UnifiedMemoryLeaseBook", "GLOBAL_METAL_LEASE_BOOK",
    "reserve_apple_llama_runtime",
]
