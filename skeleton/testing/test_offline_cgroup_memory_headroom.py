"""Adversarial cgroup memory admission tests; no hardware qualification."""
from __future__ import annotations

import os
import sys

import pytest

from skeleton.app import offline_cgroup_memory_headroom as module
from skeleton.ai.model_runtime import fair_stream_live_budget as budget_module
from skeleton.app.offline_resources import LocalResourceSnapshot


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux cgroup-v2 only")



def configure_sampler(monkeypatch):
    """Independent fixture: tests must not import sibling test modules."""
    monkeypatch.setattr(budget_module, "probe_local_resources", lambda _: LocalResourceSnapshot(
        total_ram_bytes=8_000_000_000,
        available_ram_bytes=4_000_000_000,
        total_disk_bytes=10_000_000_000,
        free_disk_bytes=5_000_000_000,
        cpu_count=8, cpu_load_ratio=0.1,
    ))
    monkeypatch.setattr(budget_module, "probe_cpu_thermal", lambda: ())
    monkeypatch.setattr(budget_module, "probe_io_pressure", lambda: None)
    monkeypatch.setattr(budget_module, "probe_cgroup_events", lambda: None)
    monkeypatch.setattr(budget_module, "probe_cpu_throttle", lambda: None)
    monkeypatch.setattr(budget_module, "probe_swap_counters", lambda: None)
    monkeypatch.setattr(budget_module, "probe_reclaim_counters", lambda: None)


def fixture(root, *, current="1048576", maximum="1073741824", high="max"):
    root.mkdir()
    (root / "memory.current").write_text(current + "\n", encoding="ascii")
    (root / "memory.max").write_text(maximum + "\n", encoding="ascii")
    (root / "memory.high").write_text(high + "\n", encoding="ascii")
    return str(root)


def test_finite_limit_and_high_watermark_take_minimum(tmp_path):
    root = fixture(tmp_path / "cg", current="1048576", high="268435456")
    sample = module.probe_cgroup_memory_headroom(root)
    assert sample.limit_bytes == 268435456
    assert sample.used_bytes == 1048576
    assert sample.headroom_bytes == 267386880
    assert sample.hard_hold is False


def test_unlimited_does_not_claim_host_memory(tmp_path):
    root = fixture(tmp_path / "cg", maximum="max", high="max")
    sample = module.probe_cgroup_memory_headroom(root)
    assert sample.limit_bytes is None
    assert sample.headroom_bytes is None
    assert sample.pressure_ppm == 0


def test_near_limit_holds_and_never_underflows(tmp_path):
    root = fixture(tmp_path / "cg", current="1073741823")
    sample = module.probe_cgroup_memory_headroom(root)
    assert sample.hard_hold
    assert sample.headroom_bytes == 1
    (tmp_path / "cg" / "memory.current").write_text("1073741825\n")
    sample = module.probe_cgroup_memory_headroom(root)
    assert sample.hard_hold
    assert sample.headroom_bytes == 0
    assert sample.pressure_ppm == 1_000_000


@pytest.mark.parametrize("invalid", [
    "-1", "+1", "1.0", "nan", "1e9", "1 2", "", "9" * 150,
    "99999999999999999999999999999999",
])
def test_malformed_current_is_never_free_memory(tmp_path, invalid):
    root = fixture(tmp_path / "cg", current=invalid)
    with pytest.raises(module.CgroupMemoryUnavailable):
        module.probe_cgroup_memory_headroom(root)


def test_missing_v2_is_unknown_but_partial_pair_is_denied(tmp_path):
    root = tmp_path / "cg"
    root.mkdir()
    assert module.probe_cgroup_memory_headroom(str(root)) is None
    (root / "memory.max").write_text("1000\n")
    with pytest.raises(module.CgroupMemoryUnavailable, match="partial"):
        module.probe_cgroup_memory_headroom(str(root))


def test_counter_symlink_is_rejected(tmp_path):
    root = fixture(tmp_path / "cg")
    (tmp_path / "cg" / "memory.current").unlink()
    (tmp_path / "cg" / "memory.current").symlink_to("/etc/passwd")
    with pytest.raises(module.CgroupMemoryUnavailable):
        module.probe_cgroup_memory_headroom(root)


def test_current_growth_during_sampling_is_conservative(tmp_path, monkeypatch):
    root = fixture(tmp_path / "cg", current="100")
    original = module._read_value
    reads = {"current": 0}

    def growing(fd, name, *, allow_max):
        if name == "memory.current":
            reads["current"] += 1
            return 100 if reads["current"] == 1 else 800000000
        return original(fd, name, allow_max=allow_max)

    monkeypatch.setattr(module, "_read_value", growing)
    sample = module.probe_cgroup_memory_headroom(root)
    assert sample.used_bytes == 800000000
    assert sample.headroom_bytes == 1073741824 - 800000000


def test_tighter_limit_during_sampling_is_conservative(tmp_path, monkeypatch):
    root = fixture(tmp_path / "cg")
    original = module._read_value
    calls = {"max": 0}

    def tightened(fd, name, *, allow_max):
        if name == "memory.max":
            calls["max"] += 1
            return 1073741824 if calls["max"] == 1 else 134217728
        return original(fd, name, allow_max=allow_max)

    monkeypatch.setattr(module, "_read_value", tightened)
    sample = module.probe_cgroup_memory_headroom(root)
    assert sample.limit_bytes == 134217728


def test_sampler_caps_host_headroom_and_holds_at_cgroup_boundary(monkeypatch):
    configure_sampler(monkeypatch)
    monkeypatch.setattr(
        budget_module, "probe_cgroup_memory_headroom",
        lambda: module.CgroupMemoryHeadroom(
            268435456, 250000000, 18435456, 931322, True,
        ),
    )
    sampler = budget_module.LiveStreamBudgetSampler()
    budget, evidence = sampler.sample(token_budget=2048)
    assert budget.available_ram_bytes == 18435456
    assert budget.effective_slots == 0
    assert evidence["holds"]["cgroup_memory"]
    assert evidence["cgroup_memory_limit_measured"]
    assert not evidence["gpu_device_qualified"]


def test_invalid_capacity_telemetry_stops_sampler(monkeypatch):
    configure_sampler(monkeypatch)
    def unavailable():
        raise module.CgroupMemoryUnavailable("corrupt")
    monkeypatch.setattr(budget_module, "probe_cgroup_memory_headroom", unavailable)
    with pytest.raises(module.CgroupMemoryUnavailable):
        budget_module.LiveStreamBudgetSampler().sample(token_budget=10)


def test_non_linux_is_unknown_even_if_root_is_supplied(monkeypatch, tmp_path):
    monkeypatch.setattr(module.sys, "platform", "darwin")
    assert module.probe_cgroup_memory_headroom(str(tmp_path)) is None


def test_ancestor_symlink_and_parent_traversal_are_rejected(tmp_path):
    actual = tmp_path / "actual"
    root = fixture(actual)
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(module.CgroupMemoryUnavailable):
        module.probe_cgroup_memory_headroom(str(alias))
    with pytest.raises(ValueError, match="parent traversal"):
        module.probe_cgroup_memory_headroom(root + "/../actual")


def test_invalid_unlimited_observation_is_not_an_authority():
    with pytest.raises(ValueError):
        module.CgroupMemoryHeadroom(None, 0, 1, 0, False)
    with pytest.raises(ValueError):
        module.CgroupMemoryHeadroom(1024, 100, 900, 0, True)
    with pytest.raises(ValueError):
        module.CgroupMemoryHeadroom(1024, 100, 924, 0, False)


def test_nested_membership_uses_child_limit_not_host_root(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root, current="1048576", maximum="max", high="max")
    child = root / "tenant"
    fixture(child, current="125829120", maximum="134217728", high="max")
    monkeypatch.setattr(module, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(module, "_read_self_cgroup_path", lambda: ("tenant",))
    sample = module.probe_cgroup_memory_headroom()
    assert sample.limit_bytes == 134217728
    assert sample.headroom_bytes == 8388608
    assert sample.hard_hold


def test_ancestor_hold_overrides_apparently_free_child(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root, current="950000000", maximum="1000000000", high="max")
    child = root / "tenant"
    fixture(child, current="1000", maximum="500000000", high="max")
    monkeypatch.setattr(module, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(module, "_read_self_cgroup_path", lambda: ("tenant",))
    sample = module.probe_cgroup_memory_headroom()
    assert sample.limit_bytes == 1000000000
    assert sample.hard_hold


def test_cgroup_membership_change_is_not_admission(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root)
    fixture(root / "tenant")
    monkeypatch.setattr(module, "_DEFAULT_CGROUP_ROOT", str(root))
    paths = iter([("tenant",), ()])
    monkeypatch.setattr(module, "_read_self_cgroup_path", lambda: next(paths))
    with pytest.raises(module.CgroupMemoryUnavailable, match="membership changed"):
        module.probe_cgroup_memory_headroom()


def test_missing_child_or_parent_capacity_is_not_host_fallback(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root)
    (root / "tenant").mkdir()
    monkeypatch.setattr(module, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(module, "_read_self_cgroup_path", lambda: ("tenant",))
    with pytest.raises(module.CgroupMemoryUnavailable, match="unmeasured"):
        module.probe_cgroup_memory_headroom()


def test_symlinked_membership_component_denied(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root)
    outside = tmp_path / "outside"
    fixture(outside)
    (root / "tenant").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(module, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(module, "_read_self_cgroup_path", lambda: ("tenant",))
    with pytest.raises(module.CgroupMemoryUnavailable):
        module.probe_cgroup_memory_headroom()


def test_invalid_membership_from_proc_is_not_trusted(monkeypatch):
    # This validates the parser without granting a fabricated cgroup path.
    import os
    original_open = module.os.open
    original_read = module.os.read
    original_close = module.os.close
    original_fstat = module.os.fstat
    def fake_open(path, flags, *args, **kwargs):
        if path == "/proc/self/cgroup":
            return original_open(os.devnull, flags)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(module.os, "open", fake_open)
    monkeypatch.setattr(module.os, "read", lambda fd, n: b"0::/../escape\\n")
    with pytest.raises(module.CgroupMemoryUnavailable, match="unsafe"):
        module._read_self_cgroup_path()
