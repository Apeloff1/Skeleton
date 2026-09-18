from __future__ import annotations

from pathlib import Path
import sys

import pytest

from skeleton.shells import (
    ShellCommand,
    ShellExecutionError,
    ShellPolicy,
    ShellPolicyError,
    ShellRunner,
)


def _policy(tmp_path: Path, **overrides) -> ShellPolicy:
    values = {
        "executables": {"python": str(Path(sys.executable).resolve())},
        "cwd_roots": (tmp_path,),
        "allowed_env": frozenset({"SAFE_VALUE"}),
        "inherited_env": frozenset(),
        "default_timeout": 1.0,
        "max_timeout": 2.0,
        "max_output_bytes": 4096,
        "max_input_bytes": 4096,
        "max_env_bytes": 4096,
        "max_args": 16,
        "max_arg_bytes": 4096,
    }
    values.update(overrides)
    return ShellPolicy(**values)


def test_rejects_relative_executable_path(tmp_path: Path) -> None:
    with pytest.raises(ShellPolicyError):
        _policy(tmp_path, executables={"python": "python"})


def test_rejects_unknown_command(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("bash"))


def test_shell_metacharacters_remain_literal_argv(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    payload = "alpha; echo injected && touch NEVER | $(whoami)"
    result = runner.run_checked(
        ShellCommand(
            "python",
            ("-c", "import sys; print(sys.argv[1])", payload),
            cwd=tmp_path,
        )
    )
    assert result.stdout_text().strip() == payload
    assert not (tmp_path / "NEVER").exists()


def test_environment_is_not_implicitly_inherited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_VALUE", "should-not-leak")
    runner = ShellRunner(_policy(tmp_path))
    result = runner.run_checked(
        ShellCommand("python", ("-c", "import os; print(os.getenv('SECRET_VALUE', ''))"), cwd=tmp_path)
    )
    assert result.stdout_text().strip() == ""


def test_explicit_allowlisted_environment_is_forwarded(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    result = runner.run_checked(
        ShellCommand(
            "python",
            ("-c", "import os; print(os.environ['SAFE_VALUE'])"),
            cwd=tmp_path,
            env={"SAFE_VALUE": "present"},
        )
    )
    assert result.stdout_text().strip() == "present"


def test_rejects_unapproved_environment_key(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", cwd=tmp_path, env={"SECRET_VALUE": "nope"}))



def test_policy_copies_environment_allowlists(tmp_path: Path) -> None:
    allowed = {"SAFE_VALUE"}
    policy = _policy(tmp_path, allowed_env=allowed)
    allowed.add("LATE_MUTATION")
    runner = ShellRunner(policy)
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", cwd=tmp_path, env={"LATE_MUTATION": "nope"}))


def test_rejects_oversize_environment(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path, max_env_bytes=8))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", cwd=tmp_path, env={"SAFE_VALUE": "too-large"}))


def test_rejects_cwd_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    runner = ShellRunner(_policy(allowed))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", ("-c", "print('x')"), cwd=outside))


def test_timeout_terminates_process(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path, default_timeout=0.05, max_timeout=0.2))
    result = runner.run(
        ShellCommand("python", ("-c", "import time; time.sleep(2)"), cwd=tmp_path)
    )
    assert result.timed_out is True
    assert result.ok is False


def test_output_limit_terminates_flood(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path, max_output_bytes=1024))
    result = runner.run(
        ShellCommand("python", ("-c", "import sys; sys.stdout.write('x' * 100000); sys.stdout.flush()"), cwd=tmp_path)
    )
    assert result.output_limited is True
    assert len(result.stdout) + len(result.stderr) <= 1024


def test_bounded_stdin_round_trip(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    result = runner.run_checked(
        ShellCommand(
            "python",
            ("-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"),
            cwd=tmp_path,
            stdin=b"hello-shell",
        )
    )
    assert result.stdout == b"hello-shell"


def test_rejects_oversize_stdin(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path, max_input_bytes=4))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", cwd=tmp_path, stdin=b"12345"))


def test_rejects_nul_argument(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", ("bad\x00arg",), cwd=tmp_path))


def test_rejects_argument_count_over_policy(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path, max_args=1))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", ("-c", "print('x')"), cwd=tmp_path))


def test_rejects_timeout_over_policy(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path, max_timeout=1.0))
    with pytest.raises(ShellPolicyError):
        runner.run(ShellCommand("python", cwd=tmp_path, timeout=2.0))


def test_run_checked_accepts_configured_nonzero_return_code(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    result = runner.run_checked(
        ShellCommand(
            "python",
            ("-c", "raise SystemExit(7)"),
            cwd=tmp_path,
            allowed_returncodes=frozenset({7}),
        )
    )
    assert result.returncode == 7
    assert result.ok is True


def test_run_checked_error_does_not_embed_child_output(tmp_path: Path) -> None:
    runner = ShellRunner(_policy(tmp_path))
    with pytest.raises(ShellExecutionError) as caught:
        runner.run_checked(
            ShellCommand(
                "python",
                ("-c", "import sys; print('super-secret'); raise SystemExit(3)"),
                cwd=tmp_path,
            )
        )
    assert "super-secret" not in str(caught.value)
    assert caught.value.result.returncode == 3


def test_rejects_executable_replaced_after_policy_construction(tmp_path: Path) -> None:
    executable = tmp_path / "tool"
    executable.write_bytes(b"first")
    policy = ShellPolicy(
        executables={"tool": str(executable.resolve())},
        cwd_roots=(tmp_path,),
    )
    runner = ShellRunner(policy)

    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"other")
    replacement.replace(executable)

    with pytest.raises(
        ShellPolicyError,
        match="registered executable changed after policy construction",
    ):
        runner.run(ShellCommand("tool", cwd=tmp_path))


def test_rejects_in_place_executable_mutation_after_policy_construction(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "tool"
    executable.write_bytes(b"first-version")
    policy = ShellPolicy(
        executables={"tool": str(executable.resolve())},
        cwd_roots=(tmp_path,),
    )
    runner = ShellRunner(policy)

    executable.write_bytes(b"second-version-with-different-size")

    with pytest.raises(
        ShellPolicyError,
        match="registered executable changed after policy construction",
    ):
        runner.run(ShellCommand("tool", cwd=tmp_path))
