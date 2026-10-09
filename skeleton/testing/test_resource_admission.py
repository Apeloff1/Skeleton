"""Hardware-aware sparse training policies: bounded, deterministic and offline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.training.resource_admission import (
    GIB, MIB, ResourceAdmissionError, ResourceObservation,
    observe_resources, select_sparse_profile,
)


def _observed(free: int | None, cpus: int | None) -> ResourceObservation:
    return ResourceObservation(
        physical_ram_bytes=16 * GIB if free is not None else None,
        available_ram_bytes=free, cgroup_free_bytes=None,
        logical_cpu_count=cpus, platform="linux",
        memory_source="synthetic-test", cpu_source="synthetic-test",
    )


@pytest.mark.parametrize(
    ("free", "cpus", "profile", "count"),
    [
        (None, None, "low-memory", 36),
        (16 * GIB, None, "low-memory", 36),
        (None, 16, "low-memory", 36),
        (2 * GIB, 16, "low-memory", 36),
        (3 * GIB, 2, "low-memory", 36),
        (4 * GIB, 4, "consumer", 48),
        (7 * GIB, 12, "consumer", 48),
        (10 * GIB, 4, "consumer", 48),
        (12 * GIB, 12, "workstation", 72),
    ],
)
def test_hardware_selection_is_conservative_and_deterministic(
    free: int | None, cpus: int | None, profile: str, count: int,
) -> None:
    first = select_sparse_profile(_observed(free, cpus))
    second = select_sparse_profile(_observed(free, cpus))
    assert first == second
    assert first["selected_profile"] == profile
    assert first["training_record_limit"] == count
    assert first["hardware_benchmark_performed"] is False
    assert first["weights_or_optimizer_fit_verified"] is False
    assert first["accelerator_available_claimed"] is False


def test_operator_ceiling_only_lowers_admitted_training_volume() -> None:
    source = _observed(16 * GIB, 32)
    assert select_sparse_profile(
        source, ceiling_profile="low-memory",
    )["training_record_limit"] == 36
    assert select_sparse_profile(
        source, ceiling_profile="consumer",
    )["training_record_limit"] == 48
    assert select_sparse_profile(
        source, ceiling_profile="workstation",
    )["training_record_limit"] == 72


@pytest.mark.parametrize("reserve", [-1, True, 16 * GIB + 1, 1.2, "1024"])
def test_admission_rejects_invalid_memory_reserve(reserve) -> None:
    with pytest.raises(ResourceAdmissionError, match="reserve"):
        select_sparse_profile(_observed(16 * GIB, 16), reserve_bytes=reserve)


@pytest.mark.parametrize("ceiling", ["ultra", "max", "", None])
def test_admission_rejects_unknown_profile(ceiling) -> None:
    with pytest.raises(ResourceAdmissionError, match="profile"):
        select_sparse_profile(_observed(16 * GIB, 16), ceiling_profile=ceiling)


def test_proc_meminfo_and_container_limit_are_both_considered() -> None:
    files = {
        "/proc/meminfo": "MemTotal:      33554432 kB\nMemAvailable: 29360128 kB\n",
        "/sys/fs/cgroup/memory.max": str(3 * GIB),
        "/sys/fs/cgroup/memory.current": str(2 * GIB),
    }

    def read(path: str) -> str:
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    o = observe_resources(
        platform="linux", read_text=read, cpu_count=lambda: 16,
        sysconf=lambda key: 1,
    )
    assert o.physical_ram_bytes == 32 * GIB
    assert o.cgroup_free_bytes == 1 * GIB
    assert o.available_ram_bytes == 1 * GIB
    assert select_sparse_profile(o)["selected_profile"] == "low-memory"


def test_unknown_os_falls_back_to_low_memory_without_executing_commands() -> None:
    def never_read(path: str) -> str:
        raise FileNotFoundError(path)

    observation = observe_resources(
        platform="unknown-os", read_text=never_read,
        cpu_count=lambda: None, sysconf=lambda _key: None,
    )
    assert observation.memory_source == "unknown"
    assert observation.available_ram_bytes is None
    assert select_sparse_profile(observation)["selected_profile"] == "low-memory"


def test_cgroup_max_string_is_not_converted_to_fake_infinity() -> None:
    files = {
        "/proc/meminfo": "MemTotal:       4194304 kB\nMemAvailable:  2097152 kB\n",
        "/sys/fs/cgroup/memory.max": "max",
        "/sys/fs/cgroup/memory.current": "2",
    }
    def read(path: str) -> str:
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]
    o = observe_resources(
        platform="linux", read_text=read, cpu_count=lambda: 8,
    )
    assert o.cgroup_free_bytes is None
    assert o.available_ram_bytes == 2 * GIB
    assert select_sparse_profile(o)["selected_profile"] == "low-memory"


def test_malformed_linux_meminfo_does_not_escalate_hardware_profile() -> None:
    files = {"/proc/meminfo": "MemTotal: Infinity kB\nMemAvailable: 999999999 kB\n"}
    o = observe_resources(
        platform="linux",
        read_text=lambda path: files[path],
        cpu_count=lambda: 32, sysconf=lambda _key: None,
    )
    assert o.physical_ram_bytes is None
    assert o.available_ram_bytes is None or o.available_ram_bytes < 1 << 62
    assert select_sparse_profile(o)["selected_profile"] == "low-memory"


def test_auto_cli_uses_measured_profile_and_never_raises_sample_cap(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    from scripts.training import sparse_capability as cli

    monkeypatch.setattr(
        cli, "observe_resources", lambda: _observed(16 * GIB, 32),
    )
    assert cli.main(["--profile", "auto", "--auto-ceiling", "consumer"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["hardware_profile"] == "consumer"
    assert result["hardware_profile_requested"] == "auto"
    assert result["active_training_rows"] == 48
    assert result["resource_admission"]["reason"] == "operator_profile_ceiling"
    assert result["resource_admission"]["accelerator_available_claimed"] is False
    assert cli.main([
        "--profile", "auto", "--auto-ceiling", "low-memory", "--budget", "48",
    ]) == 2
    assert "budget" in capsys.readouterr().err
    assert cli.main(["--profile", "consumer", "--reserve-mib", "1"]) == 2


def test_auto_cli_unknown_memory_keeps_minimal_training_data(capsys, monkeypatch) -> None:
    from scripts.training import sparse_capability as cli

    monkeypatch.setattr(cli, "observe_resources", lambda: _observed(None, None))
    assert cli.main(["--profile", "auto"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["hardware_profile"] == "low-memory"
    assert result["active_training_rows"] == 36
    assert result["resource_admission"]["hardware_benchmark_performed"] is False
