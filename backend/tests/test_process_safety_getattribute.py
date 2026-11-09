"""Focused regressions for direct module __getattribute__ process lookup."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_allows_literal_subprocess_getattribute_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.__getattribute__('run')(['python', '--version'], shell=False)\n",
    )
    assert findings == []


def test_rejects_literal_subprocess_getattribute_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.__getattribute__('run')('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_assigned_subprocess_getattribute_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner = subprocess.__getattribute__('Popen')\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.Popen" in finding and "shell=..." in finding for finding in findings)


def test_rejects_dynamic_subprocess_getattribute(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nname = 'run'\nsubprocess.__getattribute__(name)(['python', '--version'])\n",
    )
    assert any("dynamic __getattribute__() on subprocess" in finding for finding in findings)


def test_rejects_getattribute_through_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess as sp\nsp.__getattribute__('check_output')('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.check_output" in finding and "shell=..." in finding for finding in findings)


def test_rejects_os_system_getattribute(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import os\nos.__getattribute__('system')('echo unsafe')\n")
    assert any("os.system()" in finding for finding in findings)


def test_rejects_os_popen_getattribute_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import os\nexecute = os.__getattribute__('popen')\nexecute('echo unsafe')\n",
    )
    assert any("os.popen()" in finding for finding in findings)


def test_rejects_asyncio_shell_getattribute(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import asyncio\nasyncio.__getattribute__('create_subprocess_shell')('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)


def test_rejects_dynamic_os_getattribute(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import os\nname = 'system'\nos.__getattribute__(name)('echo unsafe')\n",
    )
    assert any("dynamic __getattribute__() on os" in finding for finding in findings)
