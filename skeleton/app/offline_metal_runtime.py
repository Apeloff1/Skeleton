"""Conservative Apple Silicon llama.cpp launch profile negotiation.

This layer changes only already-supported pinned llama.cpp CLI flags before
the *first* process launch. The real Metal backend owns allocations and GPU
synchronization. The estimates are admission hints, not DMA/coherency proofs.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import platform
import sys

from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppConfig, LlamaCppModel,
)
from .offline_resource_fabric import GPUResource, probe_gpu_resources
from .offline_resources import LocalResourceSnapshot, probe_local_resources


@dataclass(frozen=True)
class MetalLaunchReceipt:
    supported: bool
    reason: str
    requested_gpu_layers: int | None
    selected_gpu_layers: int | None
    selected_threads: int | None
    selected_batch_size: int | None
    available_ram_bytes: int | None
    metal_headroom_bytes: int | None
    gpu_transfer_verified: bool = False
    actual_backend_allocation: bool = False

    def as_dict(self) -> dict[str, int | str | bool | None]:
        return {
            "supported": self.supported,
            "reason": self.reason,
            "requested_gpu_layers": self.requested_gpu_layers,
            "selected_gpu_layers": self.selected_gpu_layers,
            "selected_threads": self.selected_threads,
            "selected_batch_size": self.selected_batch_size,
            "available_ram_bytes": self.available_ram_bytes,
            "metal_headroom_bytes": self.metal_headroom_bytes,
            "gpu_transfer_verified": self.gpu_transfer_verified,
            "actual_backend_allocation": self.actual_backend_allocation,
        }


def _apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine().lower() in {
        "arm64", "aarch64",
    }


def plan_metal_llama_launch(
    model: LlamaCppModel,
    *, hardware: LocalResourceSnapshot | None = None,
    devices: tuple[GPUResource, ...] | None = None,
) -> tuple[LlamaCppConfig, MetalLaunchReceipt]:
    """Conservatively *reduce* an operator-selected GPU offload under pressure.

    Not a capability escalation: never enables GPU layers if operator left
    them unset or set them to zero, never increases the chosen context, and
    never changes model, executable, tool or network boundary.
    """
    config = model.config
    if not _apple_silicon():
        return config, MetalLaunchReceipt(
            False, "non_apple_silicon", config.gpu_layers,
            config.gpu_layers, config.threads, config.batch_size,
            None, None,
        )
    if hardware is None:
        hardware = probe_local_resources(model.model_artifact.path)
    if devices is None:
        devices = probe_gpu_resources()
    apple = next((
        device for device in devices
        if device.vendor == "apple" and device.shared_with_system_ram
        and device.recommended_working_set_bytes is not None
        and device.current_allocated_bytes is not None
    ), None)
    if apple is None:
        # Fail closed for *offload*, without changing the rest of the pinned
        # model inference contract. CPU-only is a valid supported backend.
        return replace(config, gpu_layers=0), MetalLaunchReceipt(
            True, "metal_telemetry_unavailable_cpu_fallback",
            config.gpu_layers, 0, config.threads, config.batch_size,
            hardware.available_ram_bytes, None,
        )
    headroom = max(0, apple.recommended_working_set_bytes
                   - apple.current_allocated_bytes)
    ram = hardware.available_ram_bytes
    swap_used = (1 - hardware.free_swap_bytes / hardware.total_swap_bytes
                 if hardware.total_swap_bytes else 0)
    pressure = max(hardware.memory_pressure_ratio, swap_used * 0.75)
    cores = hardware.cpu_count
    # Avoid overcommitting GPU and CPU working sets on the same physical RAM.
    # Weight estimate uses whole GGUF file as a conservative upper envelope.
    available = max(0, min(int(headroom * 0.55),
                           int(ram * (0.40 - 0.25 * pressure))))
    blocks = model.serving_metadata.block_count
    known_kv = config.kv_bytes_per_token or (
        model.serving_metadata.kv_bytes_per_token_upper_bound
    )
    ctx = config.context_size
    requested = config.gpu_layers
    selected = 0
    reason = "gpu_explicitly_disabled"
    if (requested and blocks and known_kv and ctx
            and pressure < 0.85 and available > 0):
        # Model-specific layer sizes vary, so use a safety multiplier and
        # never imply this heuristic is a validated device memory allocation.
        per_layer = max(
            1, (model.model_artifact.size_bytes * 2 + blocks - 1) // blocks,
        )
        cache = ctx * known_kv
        gpu_kv_reserve = min(available, (cache + 1) // 2)
        scratch = min(available, config.runtime_scratch_bytes // 2)
        budget = max(0, available - gpu_kv_reserve - scratch)
        selected = min(requested, blocks, budget // per_layer)
        reason = "adapting_verified_metadata_to_unified_memory"
    elif requested and not (blocks and known_kv and ctx):
        reason = "missing_kv_or_layer_geometry_cpu_fallback"
    elif requested and (pressure >= 0.85 or not available):
        reason = "unified_memory_pressure_cpu_fallback"

    threads = min(config.threads or cores, cores)
    # Constrain the admission batch when memory pressure is high. This is a
    # launch-time change; process-level adaptive KV paging is still native.
    batch = min(
        config.batch_size or 256,
        max(1, (config.context_size or 4096) // 4),
        max(16, int(256 * max(0.125, 1 - pressure))),
    )
    updated = replace(
        config, gpu_layers=selected, threads=threads, batch_size=batch,
    )
    return updated, MetalLaunchReceipt(
        True, reason, requested, selected, threads, batch, ram, headroom,
    )


def require_live_metal_headroom(
    model: LlamaCppModel,
    *, hardware: LocalResourceSnapshot | None = None,
    devices: tuple[GPUResource, ...] | None = None,
) -> MetalLaunchReceipt:
    """Fail closed *before* launching an Apple GPU subprocess under pressure.

    A deployed llama.cpp process owns Metal allocations. An already sealed
    launch profile cannot safely be retuned mid-request. When the available
    host/Metal working set shrinks, reject this request instead of claiming
    a GPU-to-swap migration, changing model identity or launching into OOM.
    """
    if not _apple_silicon() or not model.config.gpu_layers:
        return MetalLaunchReceipt(
            False, "gpu_offload_not_active", model.config.gpu_layers,
            model.config.gpu_layers, model.config.threads,
            model.config.batch_size, None, None,
        )
    from .offline_resources import LocalResourcePressure

    planned, receipt = plan_metal_llama_launch(
        model, hardware=hardware, devices=devices,
    )
    if planned.gpu_layers is None or planned.gpu_layers < model.config.gpu_layers:
        raise LocalResourcePressure(
            "Apple unified-memory headroom no longer supports the sealed "
            "Metal offload profile; retry after pressure clears or reload "
            "with fewer GPU layers. No model state was changed."
        )
    return receipt


__all__ = [
    "MetalLaunchReceipt", "plan_metal_llama_launch",
    "require_live_metal_headroom",
]
