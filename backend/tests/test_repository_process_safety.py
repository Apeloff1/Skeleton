"""Regression tests for the repository-wide process execution policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

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
