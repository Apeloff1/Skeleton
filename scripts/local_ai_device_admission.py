#!/usr/bin/env python3
"""Read-only physical CPU/GPU/daemon admission for local Jeeves Docker.

Never call model providers, download binaries, install drivers, change
Docker settings, request privileged services or claim native GPU execution
from inventory alone. Outputs allowlisted numeric/small status fields only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_image_transfer as transfer
from scripts import local_ai_offline_compose as compose

SCHEMA = "skeleton.local-ai.docker.device-preflight.v1"
MIN_FREE_DISK = 8 * 1024 ** 3
MIN_AVAILABLE_MEMORY = 2 * 1024 ** 3
MAX_GPU_OUTPUT = 65536


class DeviceAdmissionError(host.LocalDockerError):
    """The physical local-AI device configuration cannot be admitted."""


def _bytes_from_linux_meminfo() -> int:
    path = Path("/proc/meminfo")
    try:
        data = path.read_text(encoding="ascii")[:8192]
    except (OSError, UnicodeError):
        raise DeviceAdmissionError("physical available memory unavailable") from None
    result = re.search(r"^MemAvailable:\s+(\d+)\s+kB$", data, re.M)
    if not result:
        raise DeviceAdmissionError("Linux MemAvailable missing")
    value = int(result.group(1)) * 1024
    if value < 0 or value > 1 << 63:
        raise DeviceAdmissionError("Linux memory inventory out of range")
    return value


def _safe_exec(argv: list[str], *, root: Path) -> str:
    if len(argv) > 12 or any(not isinstance(x, str) or len(x) > 128 for x in argv):
        raise DeviceAdmissionError("physical device command admission failed")
    try:
        result = subprocess.run(argv, cwd=root, text=True,
                                capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise DeviceAdmissionError("physical device interface unavailable") from None
    if (result.returncode != 0 or len(result.stdout) > MAX_GPU_OUTPUT
            or len(result.stderr) > MAX_GPU_OUTPUT):
        raise DeviceAdmissionError("physical device capability query failed")
    return result.stdout


def _nvidia(root: Path) -> tuple[int, int]:
    output = _safe_exec([
        "nvidia-smi", "--query-gpu=memory.total",
        "--format=csv,noheader,nounits",
    ], root=root)
    rows = [line.strip() for line in output.splitlines() if line.strip()]
    if not rows or len(rows) > 16:
        raise DeviceAdmissionError("NVIDIA GPU inventory absent or unbounded")
    memory: list[int] = []
    for row in rows:
        if not re.fullmatch(r"[0-9]{1,8}", row):
            raise DeviceAdmissionError("NVIDIA VRAM inventory invalid")
        mib = int(row)
        if not 1024 <= mib <= 2 * 1024 * 1024:
            raise DeviceAdmissionError("NVIDIA VRAM out of scope")
        memory.append(mib)
    return len(memory), min(memory)


def _rocm() -> tuple[int, int]:
    nodes = [Path("/dev/kfd"), Path("/dev/dri")]
    try:
        if (not stat.S_ISCHR(nodes[0].stat().st_mode)
                or not stat.S_ISDIR(nodes[1].stat().st_mode)):
            raise DeviceAdmissionError("ROCm kernel devices unavailable")
        render = [x for x in nodes[1].iterdir()
                  if re.fullmatch(r"renderD[0-9]{3}", x.name)]
        if not render or len(render) > 16 or any(
            not stat.S_ISCHR(x.stat().st_mode) for x in render
        ):
            raise DeviceAdmissionError("ROCm render nodes unavailable")
    except OSError:
        raise DeviceAdmissionError("ROCm kernel device metadata unavailable") from None
    # The kernel interface is observed, but VRAM/driver compatibility and
    # llama.cpp offload require separate physical model execution.
    return len(render), 0


def preflight_device(mode: str, *, root: Path = host.ROOT) -> dict[str, Any]:
    if mode not in host.GPU_OVERLAYS:
        raise DeviceAdmissionError("unknown Jeeves accelerator mode")
    if platform.system() != "Linux":
        raise DeviceAdmissionError("local Docker backend requires Linux/WSL2 engine")
    daemon = transfer._daemon_platform(root)
    machine = transfer._normalized_arch(platform.machine().lower())
    if "linux/" + machine != daemon:
        # WSL2 Docker Desktop engines may have a different daemon host from
        # the Python client. Do not infer hardware from client-side counters.
        raise DeviceAdmissionError("Docker daemon and host platform differ")
    canonical = compose._original(mode, root)
    service = canonical["services"]["skeleton"]
    limits = service.get("mem_limit"), service.get("cpus"), service.get("pids_limit")
    memory_limit, cpu_limit, pid_limit = limits
    if (type(memory_limit) is not int or not 512 * 1024**2 <= memory_limit <= 1024**4
            or type(cpu_limit) not in (int, float) or
            not 0.25 <= cpu_limit <= 1024
            or type(pid_limit) is not int or not 16 <= pid_limit <= 1048576):
        raise DeviceAdmissionError("effective Docker model resource limits invalid")
    available_mem = _bytes_from_linux_meminfo()
    if available_mem < MIN_AVAILABLE_MEMORY:
        raise DeviceAdmissionError("available model host memory below safe floor")
    try:
        cpus = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        raise DeviceAdmissionError("physical CPU affinity unavailable") from None
    if cpus < 1 or cpu_limit > cpus:
        raise DeviceAdmissionError("container CPU reservation exceeds host affinity")
    target = root if root.is_dir() else root.parent
    try:
        free_disk = shutil.disk_usage(target).free
    except OSError:
        raise DeviceAdmissionError("local storage capacity unavailable") from None
    if free_disk < MIN_FREE_DISK:
        raise DeviceAdmissionError("insufficient free disk for safe offline model operation")
    devices = 0
    minimum_vram_mib = 0
    if mode == "nvidia":
        devices, minimum_vram_mib = _nvidia(root)
    elif mode == "rocm":
        devices, minimum_vram_mib = _rocm()
    return {
        "schema": SCHEMA,
        "status": "physical_device_inventory_not_live_model_qualified",
        "mode": mode,
        "daemon_platform": daemon,
        "host_affinity_cpus": cpus,
        "available_host_memory_bytes": available_mem,
        "free_storage_bytes": free_disk,
        "configured_memory_limit_bytes": memory_limit,
        "configured_cpu_limit": cpu_limit,
        "configured_pid_limit": pid_limit,
        "physical_gpu_nodes_observed": devices,
        "minimum_reported_vram_mib": minimum_vram_mib,
        "device_os_linux": True,
        "cpu_capacity_preflight_passed": True,
        "physical_gpu_offload_executed": False,
        "licensed_gguf_inference_executed": False,
        "model_context_pressure_qualified": False,
        "restart_recovery_qualified": False,
        "windows_wsl2_qualified": False,
        "protected_chat_qualified": False,
        "release_qualified": False,
    }


__all__ = ["preflight_device"]
