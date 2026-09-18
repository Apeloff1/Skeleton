from pathlib import Path
import sys
import pytest

from skeleton.shells.limits import ResourceLimits
from skeleton.shells.policy import intersect_policies, is_narrower_or_equal, narrow_policy
from skeleton.shells.profiles import build_default_profiles
from skeleton.shells.runner import ShellPolicy
from skeleton.shells.session import ShellSession
from skeleton.shells.receipts import ExecutionReceipt


def policy(tmp_path, **overrides):
    values = dict(
        executables={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(tmp_path,),
        allowed_env=frozenset({"LANG", "MODE"}),
        inherited_env=frozenset({"LANG"}),
        default_timeout=10.0,
        max_timeout=60.0,
        max_output_bytes=1000,
        max_input_bytes=500,
        max_env_bytes=400,
        max_args=20,
        max_arg_bytes=200,
    )
    values.update(overrides)
    return ShellPolicy(**values)


def fake_receipt(ok=True):
    return ExecutionReceipt(
        command="python", correlation_id="c", fingerprint="f", started_at="a", finished_at="b",
        duration_ms=10, returncode=0 if ok else 1, ok=ok, timed_out=False, output_limited=False,
        stdout_bytes=2, stderr_bytes=3,
    )


def test_narrow_policy_reduces_limits_and_env(tmp_path):
    parent = policy(tmp_path)
    child = narrow_policy(parent, allowed_env={"LANG"}, max_timeout=20, max_output_bytes=100)
    assert child.allowed_env == frozenset({"LANG"})
    assert child.max_timeout == 20
    assert child.max_output_bytes == 100
    assert is_narrower_or_equal(child, parent)


def test_narrow_policy_rejects_new_env_authority(tmp_path):
    with pytest.raises(ValueError):
        narrow_policy(policy(tmp_path), allowed_env={"LANG", "SECRET"})


def test_narrow_policy_rejects_larger_limits(tmp_path):
    with pytest.raises(ValueError):
        narrow_policy(policy(tmp_path), max_output_bytes=1001)


def test_narrow_policy_rejects_outside_cwd_root(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        narrow_policy(policy(allowed), cwd_roots=(outside,))


def test_policy_intersection_uses_common_authority(tmp_path):
    child_root = tmp_path / "child"
    child_root.mkdir()
    left = policy(tmp_path, allowed_env=frozenset({"LANG", "MODE"}), max_timeout=60)
    right = policy(child_root, allowed_env=frozenset({"LANG"}), max_timeout=20)
    merged = intersect_policies(left, right)
    assert merged.cwd_roots == (child_root.resolve(),)
    assert merged.allowed_env == frozenset({"LANG"})
    assert merged.max_timeout == 20


def test_policy_intersection_rejects_no_common_executable(tmp_path):
    left = policy(tmp_path)
    right = ShellPolicy(executables={"other": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
    with pytest.raises(ValueError):
        intersect_policies(left, right)


def test_default_profiles_have_expected_relative_tightness(tmp_path):
    catalog = build_default_profiles({"python": str(Path(sys.executable).resolve())}, tmp_path)
    assert catalog.names() == ("agent-tool", "build", "inspection")
    assert catalog.get("inspection").policy.max_timeout < catalog.get("build").policy.max_timeout
    assert catalog.get("agent-tool").policy.inherited_env == frozenset()


def test_session_close_prevents_new_commands():
    session = ShellSession(ResourceLimits(max_commands=2))
    session.close()
    with pytest.raises(Exception):
        session.require_start("python")


def test_session_records_receipts_and_usage():
    session = ShellSession(ResourceLimits(max_commands=2, max_failures=2))
    session.require_start("python")
    session.record(fake_receipt(ok=False))
    snap = session.snapshot()
    assert snap.receipt_count == 1
    assert snap.usage.commands == 1
    assert snap.usage.failures == 1


def test_session_receipt_capacity_is_bounded():
    session = ShellSession(ResourceLimits(max_commands=3), max_receipts=1)
    session.require_start("python")
    session.record(fake_receipt())
    session.require_start("python")
    with pytest.raises(Exception):
        session.record(fake_receipt())
