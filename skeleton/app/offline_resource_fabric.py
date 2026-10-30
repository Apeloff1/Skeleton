"""Telemetry-driven resource fabric for the private offline application.

Plans are observational/policy suggestions; only read-only host staging and
multi-source disk streaming are implemented by this module. The llama.cpp and
native adapters alone own GPU allocation and execution. No GPU/UMA inference
capability is invented when a driver provides no trustworthy telemetry.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import mmap
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any, Iterable

from .offline_resources import (
    LocalResourcePressure, LocalResourceSnapshot, probe_local_resources,
)


class ResourceFabricError(RuntimeError):
    """The resource fabric cannot safely stage or schedule this operation."""


@dataclass(frozen=True)
class GPUResource:
    device: str
    vendor: str
    dedicated_total_bytes: int
    dedicated_free_bytes: int
    shared_total_bytes: int | None = None
    shared_free_bytes: int | None = None
    shared_with_system_ram: bool = False
    measurement: str = "unknown"

    def __post_init__(self) -> None:
        if not self.device or not self.vendor:
            raise ValueError("GPU identity required")
        for key in ("dedicated_total_bytes", "dedicated_free_bytes"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError("invalid GPU capacity")
        if self.dedicated_free_bytes > self.dedicated_total_bytes:
            raise ValueError("GPU free VRAM cannot exceed total VRAM")
        if (self.shared_total_bytes is None) != (self.shared_free_bytes is None):
            raise ValueError("shared GPU memory must have complete telemetry")
        if self.shared_total_bytes is not None and (
            type(self.shared_total_bytes) is not int
            or type(self.shared_free_bytes) is not int
            or not 0 <= self.shared_free_bytes <= self.shared_total_bytes
        ):
            raise ValueError("invalid shared memory telemetry")

    def as_dict(self) -> dict[str, Any]:
        return {
            "device": self.device, "vendor": self.vendor,
            "dedicated_total_bytes": self.dedicated_total_bytes,
            "dedicated_free_bytes": self.dedicated_free_bytes,
            "shared_total_bytes": self.shared_total_bytes,
            "shared_free_bytes": self.shared_free_bytes,
            "shared_with_system_ram": self.shared_with_system_ram,
            "measurement": self.measurement,
        }


def _read_positive(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="ascii").strip()
        return int(raw) if raw.isdecimal() else None
    except (OSError, ValueError, UnicodeError):
        return None


def probe_gpu_resources() -> tuple[GPUResource, ...]:
    """Optional NVML, then Linux DRM sysfs. Unknown is not free memory.

    NVML reports dedicated GPU memory only. GTT on AMD is host-backed and
    must never be counted as additive RAM or independent VRAM.
    """
    devices: list[GPUResource] = []
    try:
        import pynvml  # type: ignore[import-not-found]
        pynvml.nvmlInit()
        try:
            for index in range(pynvml.nvmlDeviceGetCount()):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                devices.append(GPUResource(
                    device=str(name), vendor="nvidia",
                    dedicated_total_bytes=int(memory.total),
                    dedicated_free_bytes=int(memory.free),
                    measurement="nvml",
                ))
        finally:
            pynvml.nvmlShutdown()
    except (ImportError, OSError, RuntimeError, AttributeError, ValueError):
        pass
    # Avoid double counting Nvidia devices already covered by NVML.
    if devices:
        return tuple(devices)
    try:
        entries = sorted(Path("/sys/class/drm").glob("card[0-9]*"))
    except OSError:
        return ()
    for card in entries:
        physical = card / "device"
        dedicated = _read_positive(physical / "mem_info_vram_total")
        used = _read_positive(physical / "mem_info_vram_used")
        shared = _read_positive(physical / "mem_info_gtt_total")
        shared_used = _read_positive(physical / "mem_info_gtt_used")
        if dedicated is None or used is None or used > dedicated:
            continue
        valid_shared = (
            shared is not None and shared_used is not None and shared_used <= shared
        )
        devices.append(GPUResource(
            device=card.name, vendor="drm",
            dedicated_total_bytes=dedicated,
            dedicated_free_bytes=dedicated - used,
            shared_total_bytes=shared if valid_shared else None,
            shared_free_bytes=shared - shared_used if valid_shared else None,
            shared_with_system_ram=valid_shared,
            measurement="linux_drm_sysfs",
        ))
    return tuple(devices)


@dataclass(frozen=True)
class FabricSnapshot:
    hardware: LocalResourceSnapshot
    gpus: tuple[GPUResource, ...]
    observed_ns: int
    active_streams: int
    measured_gpu: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "skeleton.offline.resource-fabric.v1",
            "observed_ns": self.observed_ns,
            "hardware": self.hardware.as_dict(),
            "gpus": [device.as_dict() for device in self.gpus],
            "gpu_telemetry_available": self.measured_gpu,
            "active_streams": self.active_streams,
            "shared_memory_is_additive": False,
            "gpu_backend_binding": "advisory_only",
        }


@dataclass(frozen=True)
class FabricPlan:
    source_bytes: int
    residency: str
    readonly_staging: bool
    stream_count: int
    transfer_chunk_bytes: int
    gpu_eligible: bool
    gpu_device: str | None
    requested_gpu_bytes: int
    dedicated_gpu_budget_bytes: int
    memory_pressure: float
    reason: str
    evidence_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_bytes": self.source_bytes,
            "residency": self.residency,
            "readonly_staging": self.readonly_staging,
            "stream_count": self.stream_count,
            "transfer_chunk_bytes": self.transfer_chunk_bytes,
            "gpu_eligible": self.gpu_eligible,
            "gpu_device": self.gpu_device,
            "requested_gpu_bytes": self.requested_gpu_bytes,
            "dedicated_gpu_budget_bytes": self.dedicated_gpu_budget_bytes,
            "memory_pressure": self.memory_pressure,
            "reason": self.reason,
            "evidence_digest": self.evidence_digest,
            "backend_gpu_transfer_executed": False,
        }


class AdaptiveResourceFabric:
    """Locked controller with smoothing/hysteresis and measurable decisions.

    A score predicts *admission pressure*, not model intelligence or model
    quality. Deterministic hard guards always override the predictor.
    """

    def __init__(self, storage_path: str | Path):
        self.storage_path = Path(storage_path)
        self._lock = threading.RLock()
        self._pressure_ema: float | None = None
        self._active_streams = 0
        self._observations = 0

    def observe(self) -> FabricSnapshot:
        hardware = probe_local_resources(self.storage_path)
        gpus = probe_gpu_resources()
        ram_pressure = 1 - hardware.available_ram_bytes / hardware.total_ram_bytes
        swap_pressure = (
            1 - hardware.free_swap_bytes / hardware.total_swap_bytes
            if hardware.total_swap_bytes else 0
        )
        pressure = max(
            hardware.memory_pressure_ratio, ram_pressure, swap_pressure * 0.75,
            min(1.0, hardware.cpu_load_ratio) * 0.35,
        )
        with self._lock:
            if self._pressure_ema is None:
                self._pressure_ema = pressure
            else:
                # Fast climb, slow recovery prevents violent oscillation.
                alpha = 0.6 if pressure > self._pressure_ema else 0.15
                self._pressure_ema += alpha * (pressure - self._pressure_ema)
            self._observations += 1
            active = self._active_streams
        return FabricSnapshot(hardware, gpus, time.time_ns(), active, bool(gpus))

    def plan(
        self, source_bytes: int, *, desired_streams: int = 1,
        requested_gpu_bytes: int = 0, allow_gpu: bool = False,
    ) -> FabricPlan:
        for value in (source_bytes, desired_streams, requested_gpu_bytes):
            if type(value) is not int or value < 0:
                raise ValueError("resource requests must be non-negative integers")
        if desired_streams == 0 or type(allow_gpu) is not bool:
            raise ValueError("invalid concurrent resource request")
        snap = self.observe()
        hw = snap.hardware
        with self._lock:
            ema = self._pressure_ema if self._pressure_ema is not None else 1.0
            running = self._active_streams
        if source_bytes > hw.disk_document_budget and source_bytes > hw.resident_document_budget:
            raise LocalResourcePressure("not enough RAM or disk headroom to stage requested source")
        residency = "disk_chunks" if (
            source_bytes > hw.resident_document_budget or hw.should_spill_early
            or ema >= 0.8
        ) else "system_ram"
        # "Read-only on-board" is host page-cache-backed immutable mmap staging.
        # On UMA systems it may be physically shared with the GPU, but without
        # an explicit driver API this is NOT a GPU-coherent allocation.
        staging = residency == "disk_chunks" or source_bytes > hw.read_chunk_bytes
        headroom = max(1, hw.suggested_index_jobs - running)
        penalty = max(1, int(1 + ema * hw.cpu_count))
        streams = max(1, min(desired_streams, headroom, max(1, hw.cpu_count // penalty)))
        gpu = None
        budget = 0
        # Never count shared GPU RAM as additional system or dedicated VRAM.
        for device in snap.gpus:
            free = int(device.dedicated_free_bytes * 0.70)
            if free > budget:
                gpu, budget = device, free
        eligible = bool(
            allow_gpu and gpu is not None and requested_gpu_bytes > 0
            and requested_gpu_bytes <= budget
        )
        reason = (
            "verified read-only host staging, SQLite spill when needed; "
            "GPU execution is exclusively backend-owned"
        )
        evidence = {
            "source_bytes": source_bytes,
            "residency": residency, "streams": streams,
            "requested_gpu_bytes": requested_gpu_bytes,
            "gpu": gpu.device if eligible and gpu else None,
            "ram_free": hw.available_ram_bytes,
            "swap_free": hw.free_swap_bytes,
            "disk_free": hw.free_disk_bytes,
            "cpu_load": hw.cpu_load_ratio,
            "predictive_pressure": round(ema, 6),
        }
        return FabricPlan(
            source_bytes=source_bytes, residency=residency,
            readonly_staging=staging, stream_count=streams,
            transfer_chunk_bytes=hw.read_chunk_bytes,
            gpu_eligible=eligible,
            gpu_device=gpu.device if eligible and gpu else None,
            requested_gpu_bytes=requested_gpu_bytes,
            dedicated_gpu_budget_bytes=budget,
            memory_pressure=round(ema, 6), reason=reason,
            evidence_digest=hashlib.sha256(
                json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )

    def monitor(self) -> dict[str, Any]:
        snapshot = self.observe()
        with self._lock:
            pressure = self._pressure_ema
            observations = self._observations
        result = snapshot.as_dict()
        result["controller"] = {
            "predictive_pressure": round(pressure or 0, 6),
            "observations": observations,
            "adaptive_stream_budget": snapshot.hardware.suggested_index_jobs,
            "mode": "adaptive_deterministic_with_predictive_smoothing",
            "gpu_allocation_authority": "inference_backend_only",
            "onboard_readonly_staging": "host_mmap_page_cache",
        }
        return result

    def stream_readonly(
        self, root: str | Path, relative_paths: Iterable[str],
        *, desired_streams: int = 4,
    ) -> tuple[dict[str, Any], ...]:
        """Verified concurrent read-only mmap streams with bounded copied chunks.

        This is *actual* disk-backed memory mapping, not a claim that the GPU
        can coherently address or write the mapping. Only regular files in the
        selected root may be staged. No raw source bytes leave this API.
        """
        base = Path(root).resolve(strict=True)
        if not base.is_dir() or Path(root).is_symlink():
            raise ResourceFabricError("trusted regular directory required")
        names = tuple(relative_paths)
        if not names or len(names) != len(set(names)):
            raise ResourceFabricError("nonempty, unique source paths required")
        if len(names) > 10000:
            raise ResourceFabricError("one request must page source identity lists")
        entries: list[tuple[str, Path, int]] = []
        total = 0
        for name in names:
            if not isinstance(name, str) or not name or "\x00" in name:
                raise ResourceFabricError("invalid source relative name")
            rel = Path(name)
            if rel.is_absolute() or any(part in {"..", "."} for part in rel.parts):
                raise ResourceFabricError("source escapes operator root")
            target = base / rel
            try:
                if any(item.is_symlink() for item in (target, *target.parents) if item != base and base in item.parents):
                    raise ResourceFabricError("source path contains symlink")
                resolved = target.resolve(strict=True)
                if not resolved.is_relative_to(base):
                    raise ResourceFabricError("source escapes operator root")
                info = target.stat()
                if not stat.S_ISREG(info.st_mode):
                    raise ResourceFabricError("source must be a regular file")
            except OSError as exc:
                raise ResourceFabricError("source cannot be safely statted") from exc
            entries.append((name, target, info.st_size))
            total += info.st_size
        plan = self.plan(total, desired_streams=desired_streams)
        # Never create 1 mmap covering the entire source; map the file
        # read-only, then read bounded spans from OS pages with no writes.
        with self._lock:
            self._active_streams += plan.stream_count
        def worker(entry: tuple[str, Path, int]) -> dict[str, Any]:
            name, path, expected_size = entry
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
                    raise ResourceFabricError("source changed before mmap admission")
                digest = hashlib.sha256()
                if before.st_size:
                    with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as view:
                        for offset in range(0, before.st_size, plan.transfer_chunk_bytes):
                            digest.update(view[offset:offset + plan.transfer_chunk_bytes])
                after = os.fstat(fd)
                current = path.lstat()
                if (
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
                ):
                    raise ResourceFabricError("source changed during staged read")
                return {
                    "source": name, "size_bytes": expected_size,
                    "sha256": digest.hexdigest(), "readonly": True,
                    "staging": "os_file_backed_mmap",
                    "gpu_coherence_verified": False,
                }
            finally:
                os.close(fd)
        try:
            with ThreadPoolExecutor(max_workers=plan.stream_count) as pool:
                futures = [pool.submit(worker, item) for item in entries]
                records = [future.result() for future in futures]
            return tuple(records)
        finally:
            with self._lock:
                self._active_streams -= plan.stream_count


__all__ = [
    "GPUResource", "FabricSnapshot", "FabricPlan", "AdaptiveResourceFabric",
    "ResourceFabricError", "probe_gpu_resources",
]
