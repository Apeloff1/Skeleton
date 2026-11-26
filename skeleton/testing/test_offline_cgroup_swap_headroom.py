"""Deterministic cgroup-v2 swap spill admission tests; no device qualification."""
from __future__ import annotations

import sys

import pytest

from skeleton.app import offline_cgroup_swap_headroom as swap
from skeleton.ai.model_runtime import fair_stream_live_budget as budget_module
from skeleton.app.offline_resources import LocalResourceSnapshot

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux cgroup-v2 only")


def fixture(path, *, used="1048576", maximum="268435456"):
    path.mkdir()
    (path / "memory.swap.current").write_text(used + "\n", encoding="ascii")
    (path / "memory.swap.max").write_text(maximum + "\n", encoding="ascii")
    return str(path)


def test_bounded_swap_headroom_is_not_ram_capacity(tmp_path):
    root = fixture(tmp_path / "cg")
    result = swap.probe_cgroup_swap_headroom(root)
    assert result.limit_bytes == 268435456
    assert result.headroom_bytes == 267386880
    assert result.spill_allowed
    assert result.pressure_ppm > 0


def test_no_swap_does_not_authorize_spill(tmp_path):
    root = fixture(tmp_path / "cg", used="0", maximum="0")
    result = swap.probe_cgroup_swap_headroom(root)
    assert result.headroom_bytes == 0
    assert not result.spill_allowed
    assert result.pressure_ppm == 0


def test_unlimited_is_not_a_finite_reservation(tmp_path):
    root = fixture(tmp_path / "cg", maximum="max")
    result = swap.probe_cgroup_swap_headroom(root)
    assert result.limit_bytes is None
    assert result.headroom_bytes is None
    assert not result.spill_allowed


def test_over_limit_stays_denied(tmp_path):
    root = fixture(tmp_path / "cg", used="400000000", maximum="268435456")
    result = swap.probe_cgroup_swap_headroom(root)
    assert result.headroom_bytes == 0
    assert result.pressure_ppm == 1000000
    assert not result.spill_allowed


@pytest.mark.parametrize("invalid", ["-1", "+1", "nan", "1 2", "9" * 150])
def test_malformed_swap_counters_fail_closed(tmp_path, invalid):
    root = fixture(tmp_path / "cg", used=invalid)
    with pytest.raises(swap.CgroupSwapUnavailable):
        swap.probe_cgroup_swap_headroom(root)


def test_partial_swap_pair_is_not_unlimited(tmp_path):
    root = tmp_path / "cg"
    root.mkdir()
    assert swap.probe_cgroup_swap_headroom(str(root)) is None
    (root / "memory.swap.current").write_text("10\n")
    with pytest.raises(swap.CgroupSwapUnavailable, match="partial"):
        swap.probe_cgroup_swap_headroom(str(root))


def test_swap_counter_symlink_denied(tmp_path):
    root = fixture(tmp_path / "cg")
    (tmp_path / "cg" / "memory.swap.current").unlink()
    (tmp_path / "cg" / "memory.swap.current").symlink_to("/etc/passwd")
    with pytest.raises(swap.CgroupSwapUnavailable):
        swap.probe_cgroup_swap_headroom(root)


def test_usage_growth_takes_worst_case(tmp_path, monkeypatch):
    root = fixture(tmp_path / "cg")
    original = swap._read_value
    calls = 0

    def growing(fd, name, *, allow_max):
        nonlocal calls
        if name == "memory.swap.current":
            calls += 1
            return 1 if calls == 1 else 267000000
        return original(fd, name, allow_max=allow_max)

    monkeypatch.setattr(swap, "_read_value", growing)
    assert not swap.probe_cgroup_swap_headroom(root).spill_allowed


def test_limit_shrink_takes_worst_case(tmp_path, monkeypatch):
    root = fixture(tmp_path / "cg")
    original = swap._read_value
    calls = 0

    def shrinking(fd, name, *, allow_max):
        nonlocal calls
        if name == "memory.swap.max":
            calls += 1
            return 268435456 if calls == 1 else 1048576
        return original(fd, name, allow_max=allow_max)

    monkeypatch.setattr(swap, "_read_value", shrinking)
    assert not swap.probe_cgroup_swap_headroom(root).spill_allowed


def test_parent_swap_exhaustion_overrides_child(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root, used="267000000")
    fixture(root / "tenant", used="100", maximum="536870912")
    monkeypatch.setattr(swap, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(swap, "_read_self_cgroup_path", lambda: ("tenant",))
    result = swap.probe_cgroup_swap_headroom()
    assert not result.spill_allowed
    assert result.limit_bytes == 268435456


def test_missing_parent_swap_controller_never_grants_spill(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    root.mkdir()
    fixture(root / "tenant")
    monkeypatch.setattr(swap, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(swap, "_read_self_cgroup_path", lambda: ("tenant",))
    assert swap.probe_cgroup_swap_headroom() is None


def test_membership_change_denied(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root)
    fixture(root / "tenant")
    monkeypatch.setattr(swap, "_DEFAULT_CGROUP_ROOT", str(root))
    membership = iter([("tenant",), ()])
    monkeypatch.setattr(swap, "_read_self_cgroup_path", lambda: next(membership))
    with pytest.raises(swap.CgroupSwapUnavailable, match="membership changed"):
        swap.probe_cgroup_swap_headroom()


def test_bad_ancestor_symlink_denied(tmp_path):
    root = fixture(tmp_path / "cg")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(swap.CgroupSwapUnavailable):
        swap.probe_cgroup_swap_headroom(str(alias))


def test_invalid_dataclass_cannot_claim_spill_authority():
    with pytest.raises(ValueError):
        swap.CgroupSwapHeadroom(None, 0, 1, 0, True)
    with pytest.raises(ValueError):
        swap.CgroupSwapHeadroom(0, 0, 0, 0, True)


def test_unlimited_boolean_pressure_is_not_valid_telemetry():
    with pytest.raises(ValueError):
        swap.CgroupSwapHeadroom(None, 0, None, False, False)


def test_leaf_inode_replacement_during_swap_sampling_denied(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root)
    fixture(root / "tenant", used="100")
    monkeypatch.setattr(swap, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(swap, "_read_self_cgroup_path", lambda: ("tenant",))
    original = swap._sample_directory
    changed = False

    def replace_leaf(fd):
        nonlocal changed
        result = original(fd)
        if result is not None and result.used_bytes == 100 and not changed:
            changed = True
            (root / "tenant").rename(root / "detached")
            fixture(root / "tenant", used="100")
        return result

    monkeypatch.setattr(swap, "_sample_directory", replace_leaf)
    with pytest.raises(swap.CgroupSwapUnavailable, match="inode replaced"):
        swap.probe_cgroup_swap_headroom()


def test_parent_swap_counter_missing_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    fixture(root)
    fixture(root / "tenant")
    (root / "memory.swap.max").unlink()
    monkeypatch.setattr(swap, "_DEFAULT_CGROUP_ROOT", str(root))
    monkeypatch.setattr(swap, "_read_self_cgroup_path", lambda: ("tenant",))
    with pytest.raises(swap.CgroupSwapUnavailable, match="partial"):
        swap.probe_cgroup_swap_headroom()
