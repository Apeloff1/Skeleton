"""Focused regressions for subprocess argument-vector enforcement."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_rejects_literal_string_subprocess_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run('python --version', check=True)\n",
    )
    assert any("argument vector" in finding for finding in findings)


def test_rejects_f_string_subprocess_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'file.txt'\nsubprocess.run(f'cat {name}', check=True)\n",
    )
    assert any("argument vector" in finding for finding in findings)


def test_rejects_concatenated_string_subprocess_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'file.txt'\nsubprocess.run('cat ' + name, check=True)\n",
    )
    assert any("argument vector" in finding for finding in findings)


def test_rejects_format_built_subprocess_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'file.txt'\nsubprocess.run('cat {}'.format(name), check=True)\n",
    )
    assert any("argument vector" in finding for finding in findings)


def test_rejects_keyword_string_subprocess_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run(args='python --version', check=True)\n",
    )
    assert any("argument vector" in finding for finding in findings)


def test_rejects_partial_bound_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools\nimport subprocess\nrunner = functools.partial(subprocess.run, 'python --version')\nrunner(check=True)\n",
    )
    assert any("partial command must be an argument vector" in finding for finding in findings)


def test_rejects_partial_keyword_string_command(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools\nimport subprocess\nrunner = functools.partial(subprocess.run, args='python --version')\nrunner(check=True)\n",
    )
    assert any("partial args=" in finding for finding in findings)


def test_allows_literal_argument_vector(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run(['python', '--version'], check=True)\n",
    )
    assert findings == []


def test_metacharacters_remain_valid_literal_argv_data(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run(['printf', '%s', '$(touch /tmp/pwned); rm -rf /'], check=True)\n",
    )
    assert findings == []


def test_allows_dynamic_argument_vector_variable(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nargv = ['python', '--version']\nsubprocess.run(argv, check=True)\n",
    )
    assert findings == []
