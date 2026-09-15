"""Regression tests for the repository-wide process execution policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "check_repository_process_safety.py"
SPEC = importlib.util.spec_from_file_location("repository_process_safety", GATE_PATH)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return GATE.violations(target)


def test_allows_argument_vector_with_hostile_metacharacters(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\n"
        "subprocess.run(['printf', '%s', 'safe; touch /tmp/never && echo nope | cat'], check=True)\n",
    )
    assert findings == []


def test_rejects_literal_string_command(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import subprocess\nsubprocess.run('python --version', check=True)\n")
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_literal_string_even_with_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run('python --version', shell=False, check=True)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_fstring_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'python'\nsubprocess.run(f'{name} --version', shell=False)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_concatenated_literal_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run('python ' + '--version', shell=False)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_concatenated_dynamic_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nexecutable = 'python'\nsubprocess.run(executable + ' --version', shell=False)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_percent_formatted_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'python'\nsubprocess.run('%s --version' % name, shell=False)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_dot_format_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'python'\nsubprocess.run('{} --version'.format(name), shell=False)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_join_built_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nparts = ['python', '--version']\nsubprocess.run(' '.join(parts), shell=False)\n",
    )
    assert any("argument vector, not a string" in finding for finding in findings)


def test_rejects_string_passed_by_args_keyword(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from subprocess import run as execute\nexecute(args='python --version', shell=False)\n",
    )
    assert any("subprocess.run" in finding and "argument vector" in finding for finding in findings)


def test_metacharacters_are_literal_runtime_arguments() -> None:
    payload = "alpha; echo injected && touch /tmp/never | $(whoami)"
    result = subprocess.run(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", payload],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == payload


def test_scan_fails_closed_when_required_root_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (tmp_path / "missing",))

    with pytest.raises(GATE.ScanCoverageError, match="scan root metadata failure"):
        list(GATE.python_files())


def test_scan_fails_closed_when_required_root_has_no_python_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "README.txt").write_text("not code\n", encoding="utf-8")
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (root,))

    with pytest.raises(GATE.ScanCoverageError, match="no regular Python files"):
        list(GATE.python_files())


def test_scan_skips_symlinked_python_files_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    real = root / "real.py"
    real.write_text("x = 1\n", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.py"
    secret.write_text("raise RuntimeError('must not be scanned')\n", encoding="utf-8")
    (root / "linked.py").symlink_to(secret)
    (root / "linked_dir").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (root,))

    assert list(GATE.python_files()) == [real]


def test_traversal_failure_is_sanitized_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "real.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (root,))

    def broken_walk(*args, onerror=None, **kwargs):
        assert onerror is not None
        onerror(PermissionError(13, "sensitive raw detail", str(root / "private")))
        return iter(())

    monkeypatch.setattr(GATE.os, "walk", broken_walk)

    with pytest.raises(GATE.ScanCoverageError) as caught:
        list(GATE.python_files())

    message = str(caught.value)
    assert "PermissionError" in message
    assert "sensitive raw detail" not in message
    assert str(tmp_path) not in message


def test_main_returns_distinct_code_for_incomplete_scan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def incomplete_scan():
        raise GATE.ScanCoverageError("coverage lost")
        yield  # pragma: no cover

    monkeypatch.setattr(GATE, "python_files", incomplete_scan)

    assert GATE.main() == 2
    captured = capsys.readouterr()
    assert "scan incomplete" in captured.err
    assert "coverage lost" in captured.err
