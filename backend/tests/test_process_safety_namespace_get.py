"""Regressions for process callables recovered through module namespace mapping get()."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_allows_vars_get_subprocess_with_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nvars(subprocess).get('run')(['python', '--version'], shell=False)\n",
    )
    assert findings == []


def test_allows_dunder_dict_get_subprocess_with_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.__dict__.get('run')(['python', '--version'], shell=False)\n",
    )
    assert findings == []


def test_rejects_vars_get_subprocess_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nvars(subprocess).get('run')('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_dunder_dict_get_subprocess_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.__dict__.get('Popen')('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.Popen" in finding and "shell=..." in finding for finding in findings)


def test_rejects_assigned_vars_get_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner = vars(subprocess).get('check_output')\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.check_output" in finding and "shell=..." in finding for finding in findings)


def test_rejects_dynamic_vars_get_key(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'run'\nvars(subprocess).get(name)(['python', '--version'])\n",
    )
    assert any("dynamic namespace get() on subprocess" in finding for finding in findings)


def test_rejects_dynamic_dunder_dict_get_key(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'run'\nsubprocess.__dict__.get(name)(['python', '--version'])\n",
    )
    assert any("dynamic namespace get() on subprocess" in finding for finding in findings)


def test_rejects_vars_get_os_system(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import os\nvars(os).get('system')('echo unsafe')\n")
    assert any("os.system()" in finding for finding in findings)


def test_rejects_dunder_dict_get_os_popen(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import os\nos.__dict__.get('popen')('echo unsafe')\n")
    assert any("os.popen()" in finding for finding in findings)


def test_rejects_vars_get_asyncio_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import asyncio\nvars(asyncio).get('create_subprocess_shell')('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)
