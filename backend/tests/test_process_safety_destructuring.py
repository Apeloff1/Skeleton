"""Focused regressions for destructured process-call alias tracking."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_allows_tuple_destructured_subprocess_alias_with_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner, marker = subprocess.run, object()\nrunner(['python', '--version'], shell=False)\n",
    )
    assert findings == []


def test_rejects_tuple_destructured_subprocess_alias_with_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner, marker = subprocess.run, object()\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_list_destructured_subprocess_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\n[runner, marker] = [subprocess.Popen, object()]\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.Popen" in finding and "shell=..." in finding for finding in findings)


def test_rejects_nested_destructured_subprocess_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\n((runner, marker), tail) = ((subprocess.check_output, object()), object())\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.check_output" in finding and "shell=..." in finding for finding in findings)


def test_rejects_destructured_os_system_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import os\nexecute, marker = os.system, object()\nexecute('echo unsafe')\n",
    )
    assert any("os.system()" in finding for finding in findings)


def test_rejects_destructured_os_popen_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import os\nexecute, marker = os.popen, object()\nexecute('echo unsafe')\n",
    )
    assert any("os.popen()" in finding for finding in findings)


def test_rejects_destructured_asyncio_shell_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import asyncio\nspawn, marker = asyncio.create_subprocess_shell, object()\nspawn('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)


def test_ignores_unresolvable_mismatched_destructuring(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner, marker = (subprocess.run,)\n",
    )
    assert findings == []
