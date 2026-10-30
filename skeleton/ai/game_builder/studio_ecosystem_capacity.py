"""Adaptive local producer-work admission from measured host CPU/RAM/disk facts.

Only READ system capacity. No kernel limits, firmware memory or GPU allocations
are modified, and GPU headroom is never inferred from host RAM.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from .studio_ecosystem_quest import StudioQuestError


@dataclass(frozen=True, slots=True)
class ProducerCapacity:
    free_ram_bytes: int
    free_disk_bytes: int
    cpu_cores: int
    gpu_free_bytes: int | None = None


def observe_producer_capacity(root: Path) -> ProducerCapacity:
    if root.is_symlink() or not root.is_dir():
        raise StudioQuestError("existing non-symlink capacity root required")
    try:
        free_disk=shutil.disk_usage(root).free
        cores=os.cpu_count() or 1
        if hasattr(os,"sysconf"):
            free_ram=int(os.sysconf("SC_AVPHYS_PAGES"))*int(os.sysconf("SC_PAGE_SIZE"))
        else:
            import psutil
            free_ram=int(psutil.virtual_memory().available)
    except (OSError,ValueError,ImportError,KeyError) as exc:
        raise StudioQuestError("host memory/disk availability not observable") from exc
    if not free_disk or not free_ram:
        raise StudioQuestError("capacity measurement unavailable")
    return ProducerCapacity(free_ram,free_disk,cores)


def plan_producer_admission(capacity: ProducerCapacity, *,
                            working_set_bytes: int,
                            output_bytes: int, gpu_bytes: int = 0) -> dict[str, object]:
    """Calculate slots from actual resource pressure, not arbitrary file counts."""
    if not isinstance(capacity,ProducerCapacity):
        raise StudioQuestError("missing capacity evidence")
    fields=(capacity.free_ram_bytes,capacity.free_disk_bytes,capacity.cpu_cores,
            working_set_bytes,output_bytes,gpu_bytes)
    if (any(type(x) is not int for x in fields) or
            min(fields[:5])<=0 or gpu_bytes<0 or
            (capacity.gpu_free_bytes is not None and
             (type(capacity.gpu_free_bytes) is not int or capacity.gpu_free_bytes<0))):
        raise StudioQuestError("invalid resource observation")
    # Reserve 20% RAM and 5% disk as measured pressure safety margins.
    ram_room=capacity.free_ram_bytes-capacity.free_ram_bytes//5
    disk_room=capacity.free_disk_bytes-capacity.free_disk_bytes//20
    slots=min(capacity.cpu_cores,ram_room//working_set_bytes,disk_room//output_bytes)
    if gpu_bytes:
        if capacity.gpu_free_bytes is None:
            slots=0
        else:
            slots=min(slots,(capacity.gpu_free_bytes-capacity.gpu_free_bytes//5)//gpu_bytes)
    return {"schema":"skeleton.game_builder.studio_adaptive_admission.v1",
            "admitted_worker_slots":max(0,slots),
            "measured_free_ram_bytes":capacity.free_ram_bytes,
            "measured_free_disk_bytes":capacity.free_disk_bytes,
            "gpu_capacity_known":capacity.gpu_free_bytes is not None,
            "native_gpu_allocation_performed":False,
            "release_certified":False}
