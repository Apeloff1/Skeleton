from pathlib import Path
import sys

from skeleton.shells.failure import FailureKind, classify_result
from skeleton.shells.policy import narrow_policy
from skeleton.shells.policy_diff import diff_policies
from skeleton.shells.runner import ShellPolicy, ShellResult


def policy(tmp_path, **overrides):
    values = dict(
        executables={"python": str(Path(sys.executable).resolve())},
        cwd_roots=(tmp_path,),
        allowed_env=frozenset({"LANG"}),
        inherited_env=frozenset(),
        max_timeout=60,
        max_output_bytes=1000,
        max_input_bytes=1000,
        max_env_bytes=1000,
        max_args=20,
        max_arg_bytes=1000,
    )
    values.update(overrides)
    return ShellPolicy(**values)


def test_failure_classifies_success():
    result = ShellResult("python", 0, b"", b"", accepted=True)
    classification = classify_result(result)
    assert classification.kind is FailureKind.NONE
    assert not classification.failed


def test_failure_classifies_timeout_before_exit_code():
    result = ShellResult("python", -15, b"", b"", timed_out=True, accepted=False)
    classification = classify_result(result)
    assert classification.kind is FailureKind.TIMEOUT
    assert classification.retryable_hint


def test_failure_classifies_output_limit_as_nonretryable_hint():
    result = ShellResult("python", -15, b"", b"", output_limited=True, accepted=False)
    classification = classify_result(result)
    assert classification.kind is FailureKind.OUTPUT_LIMIT
    assert not classification.retryable_hint


def test_failure_classifies_transient_exit_code():
    result = ShellResult("python", 75, b"", b"", accepted=False)
    classification = classify_result(result)
    assert classification.kind is FailureKind.EXIT_CODE
    assert classification.retryable_hint


def test_failure_classifies_signal_style_negative_code():
    result = ShellResult("python", -9, b"", b"", accepted=False)
    assert classify_result(result).kind is FailureKind.TERMINATED


def test_policy_diff_marks_narrowing(tmp_path):
    before = policy(tmp_path)
    after = narrow_policy(before, allowed_env=frozenset(), max_timeout=20, max_output_bytes=500)
    diff = diff_policies(before, after)
    assert not diff.wider
    assert diff.narrower_or_equal
    assert all(change.authority == "narrower" for change in diff.changes)


def test_policy_diff_marks_wider_limit(tmp_path):
    before = policy(tmp_path, max_output_bytes=100)
    after = policy(tmp_path, max_output_bytes=200)
    diff = diff_policies(before, after)
    assert diff.wider
    assert not diff.narrower_or_equal
    assert any(change.field == "max_output_bytes" and change.authority == "wider" for change in diff.changes)


def test_policy_diff_marks_added_env_key_wider(tmp_path):
    before = policy(tmp_path, allowed_env=frozenset())
    after = policy(tmp_path, allowed_env=frozenset({"LANG"}))
    diff = diff_policies(before, after)
    assert diff.wider
    assert any(change.field == "allowed_env" for change in diff.changes)
