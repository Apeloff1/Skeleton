"""Physical Docker host/CPU/GPU admission: no model, network or device mutation."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import pytest

from scripts import local_ai_device_admission as device


def _environment(monkeypatch, *, mode="cpu", mem=4 * 1024**3,
                 cores=8, free_mem=16 * 1024**3, free_disk=40 * 1024**3):
    calls = []
    monkeypatch.setattr(device.platform, "system", lambda: "Linux")
    monkeypatch.setattr(device.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(device.transfer, "_daemon_platform",
                        lambda root: "linux/amd64")
    monkeypatch.setattr(device.compose, "_original",
                        lambda actual, root: {
                            "services": {"skeleton": {
                                "mem_limit": mem, "cpus": 4.0,
                                "pids_limit": 512,
                            }},
                        })
    monkeypatch.setattr(device, "_bytes_from_linux_meminfo",
                        lambda: free_mem)
    monkeypatch.setattr(device.os, "sched_getaffinity",
                        lambda pid: set(range(cores)))
    monkeypatch.setattr(device.shutil, "disk_usage",
                        lambda where: SimpleNamespace(free=free_disk))
    monkeypatch.setattr(device, "_nvidia",
                        lambda root: (calls.append("nvidia") or (2, 16384)))
    monkeypatch.setattr(device, "_rocm",
                        lambda: (calls.append("rocm") or (1, 0)))
    return calls


@pytest.mark.parametrize("mode, count, minimum", [
    ("cpu", 0, 0), ("nvidia", 2, 16384), ("rocm", 1, 0),
])
def test_device_preflight_is_read_only_and_cannot_claim_live_gguf(
    mode, count, minimum, tmp_path, monkeypatch,
):
    calls = _environment(monkeypatch)
    report = device.preflight_device(mode, root=tmp_path)
    assert report["mode"] == mode
    assert report["daemon_platform"] == "linux/amd64"
    assert report["physical_gpu_nodes_observed"] == count
    assert report["minimum_reported_vram_mib"] == minimum
    assert report["cpu_capacity_preflight_passed"] is True
    assert report["physical_gpu_offload_executed"] is False
    assert report["licensed_gguf_inference_executed"] is False
    assert report["model_context_pressure_qualified"] is False
    assert report["windows_wsl2_qualified"] is False
    assert report["protected_chat_qualified"] is False
    assert report["release_qualified"] is False
    assert calls == ([] if mode == "cpu" else [mode])


@pytest.mark.parametrize("value", ["NVIDIA", "remote", "cuda", "", None])
def test_unknown_device_mode_denied_without_probing(value, tmp_path, monkeypatch):
    calls = _environment(monkeypatch)
    with pytest.raises(device.DeviceAdmissionError, match="unknown"):
        device.preflight_device(value, root=tmp_path)
    assert calls == []


def test_wrong_daemon_platform_denied(tmp_path, monkeypatch):
    _environment(monkeypatch)
    monkeypatch.setattr(device.transfer, "_daemon_platform",
                        lambda root: "linux/arm64")
    with pytest.raises(device.DeviceAdmissionError, match="differ"):
        device.preflight_device("cpu", root=tmp_path)


@pytest.mark.parametrize("available", [0, 1024, 1024**3])
def test_low_memory_pressure_denied(tmp_path, monkeypatch, available):
    _environment(monkeypatch, free_mem=available)
    with pytest.raises(device.DeviceAdmissionError, match="memory"):
        device.preflight_device("cpu", root=tmp_path)


@pytest.mark.parametrize("free_disk", [0, 1024, 4 * 1024**3])
def test_low_storage_denied(tmp_path, monkeypatch, free_disk):
    _environment(monkeypatch, free_disk=free_disk)
    with pytest.raises(device.DeviceAdmissionError, match="disk"):
        device.preflight_device("cpu", root=tmp_path)


def test_cpus_exceed_usable_affinity_denied(tmp_path, monkeypatch):
    _environment(monkeypatch, cores=2)
    with pytest.raises(device.DeviceAdmissionError, match="affinity"):
        device.preflight_device("cpu", root=tmp_path)


@pytest.mark.parametrize("memory,cpu,pids", [
    (0, 4, 512), (4 * 1024**3, 0, 512),
    (4 * 1024**3, 4, 0), (True, 4, 512),
    (4 * 1024**3, "4", 512), (4 * 1024**3, 4, True),
])
def test_invalid_effective_limits_fail_closed(
    tmp_path, monkeypatch, memory, cpu, pids,
):
    _environment(monkeypatch)
    monkeypatch.setattr(device.compose, "_original",
                        lambda mode, root: {"services": {"skeleton": {
                            "mem_limit": memory, "cpus": cpu, "pids_limit": pids,
                        }}})
    with pytest.raises(device.DeviceAdmissionError, match="resource limits"):
        device.preflight_device("cpu", root=tmp_path)


@pytest.mark.parametrize("gpu", [
    "", "N/A", "16384 MiB", "-1", "0", "200000000", "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n13\n14\n15\n16\n17",
])
def test_nvidia_inventory_invalid_values_denied(tmp_path, monkeypatch, gpu):
    monkeypatch.setattr(device, "_safe_exec", lambda argv, root: gpu)
    with pytest.raises(device.DeviceAdmissionError):
        device._nvidia(tmp_path)


def test_nvidia_real_memory_inventory_values_strict(tmp_path, monkeypatch):
    monkeypatch.setattr(device, "_safe_exec",
                        lambda argv, root: "24576\n16384\n")
    assert device._nvidia(tmp_path) == (2, 16384)


def test_windows_docker_client_must_not_claim_linux_hardware(tmp_path, monkeypatch):
    _environment(monkeypatch)
    monkeypatch.setattr(device.platform, "system", lambda: "Windows")
    with pytest.raises(device.DeviceAdmissionError, match="Linux"):
        device.preflight_device("cpu", root=tmp_path)
