"""Read-only hardware resource telemetry for local original game production.

Distinguishes physical RAM, OS swap, disk capacity and unknown GPU memory.
No firmware or VM settings are changed. An unmeasured GPU budget is NEVER
inferred from shared CPU RAM, including unified-memory machines.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from .studio_ecosystem_quest import StudioQuestError

@dataclass(frozen=True, slots=True)
class MemoryTelemetry:
    physical_available: int
    physical_total: int
    swap_available: int | None
    swap_total: int | None
    disk_available: int
    cpu_cores: int
    gpu_available: int | None = None
    gpu_memory_is_shared: bool | None = None


def sample_studio_memory(root: Path) -> MemoryTelemetry:
    root=Path(root)
    if root.is_symlink() or not root.is_dir():
        raise StudioQuestError("memory observation requires an existing directory")
    try:
        import psutil
    except ImportError:
        psutil=None
    try:
        disk=shutil.disk_usage(root).free
        cpus=os.cpu_count() or 1
        if psutil is not None:
            vm=psutil.virtual_memory()
            sw=psutil.swap_memory()
            available=int(vm.available)
            total=int(vm.total)
            swap_available=max(0,int(sw.free))
            swap_total=max(0,int(sw.total))
        else:
            # Fail closed on unsupported host telemetry rather than invent
            # either swap capacity or platform-specific unified VRAM.
            if not hasattr(os,"sysconf"):
                raise StudioQuestError("physical memory not observable")
            page=int(os.sysconf("SC_PAGE_SIZE"))
            available=int(os.sysconf("SC_AVPHYS_PAGES"))*page
            total=int(os.sysconf("SC_PHYS_PAGES"))*page
            swap_available=None
            swap_total=None
    except (OSError,ValueError,KeyError,AttributeError) as exc:
        raise StudioQuestError("host memory telemetry unavailable") from exc
    if min(disk,cpus,available,total)<=0 or available>total:
        raise StudioQuestError("invalid measured system memory counters")
    return MemoryTelemetry(available,total,swap_available,swap_total,
                           disk,cpus,gpu_available=None,gpu_memory_is_shared=None)


def memory_admission(telemetry: MemoryTelemetry, *, working_bytes: int,
                     spill_bytes: int = 0,
                     gpu_bytes: int = 0) -> dict[str,object]:
    if not isinstance(telemetry,MemoryTelemetry):
        raise StudioQuestError("missing memory observation")
    values=(telemetry.physical_available,telemetry.physical_total,
            telemetry.disk_available,telemetry.cpu_cores,working_bytes,
            spill_bytes,gpu_bytes)
    if (any(type(v) is not int for v in values) or
            min(values[:5])<=0 or min(values[5:])<0 or
            telemetry.physical_available>telemetry.physical_total):
        raise StudioQuestError("invalid memory estimate")
    ram_room=telemetry.physical_available-telemetry.physical_available//5
    disk_room=telemetry.disk_available-telemetry.disk_available//20
    # Explicit spill path is persisted on app-owned disk, NOT OS swap and
    # never counted twice as both GPU and CPU physical RAM.
    max_slots=min(telemetry.cpu_cores,ram_room//working_bytes)
    if spill_bytes:
        max_slots=min(max_slots,disk_room//spill_bytes)
    if gpu_bytes:
        free=telemetry.gpu_available
        if free is None or type(free) is not int or free<0:
            max_slots=0
        elif telemetry.gpu_memory_is_shared is True:
            max_slots=min(max_slots,ram_room//(working_bytes+gpu_bytes))
        else:
            max_slots=min(max_slots,(free-free//5)//gpu_bytes)
    return {"schema":"skeleton.game_builder.local_memory_admission.v1",
            "admitted_slots":max(0,max_slots),
            "ram_free":telemetry.physical_available,
            "swap_free_observed":telemetry.swap_available,
            "disk_free":telemetry.disk_available,
            "gpu_memory_independently_known":telemetry.gpu_available is not None,
            "shared_gpu_ram_double_counted":False,
            "app_disk_spill_enabled":spill_bytes>0,
            "os_virtual_memory_modified":False,
            "release_certified":False}
