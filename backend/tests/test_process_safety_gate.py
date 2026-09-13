"""Regression tests for the dependency-free process invocation safety gate."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_allows_argument_vector_subprocess(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run(['python', '--version'], check=True)\n",
    )
    assert findings == []


def test_allows_explicit_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run(['python', '--version'], shell=False, check=True)\n",
    )
    assert findings == []


def test_allows_assigned_subprocess_alias_with_literal_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner = subprocess.run\nrunner(['python', '--version'], shell=False)\n",
    )
    assert findings == []


def test_rejects_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run('echo unsafe', shell=True)\n",
    )
    assert any("shell=..." in finding for finding in findings)


def test_rejects_dynamic_shell_value(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nuse_shell = False\nsubprocess.run('echo unsafe', shell=use_shell)\n",
    )
    assert any("shell=..." in finding for finding in findings)


def test_rejects_opaque_subprocess_kwargs(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\noptions = {'shell': False}\nsubprocess.run('echo unsafe', **options)\n",
    )
    assert any("**kwargs" in finding for finding in findings)


def test_rejects_opaque_kwargs_through_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from subprocess import run as execute\noptions = {'check': True}\nexecute(['python', '--version'], **options)\n",
    )
    assert any("subprocess.run" in finding and "**kwargs" in finding for finding in findings)


def test_rejects_assigned_subprocess_callable_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner = subprocess.run\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_chained_assigned_subprocess_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner = subprocess.run\nexecute = runner\nexecute('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_annotated_assigned_subprocess_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nrunner: object = subprocess.run\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_subprocess_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess as sp\nsp.Popen('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.Popen" in finding for finding in findings)


def test_rejects_direct_subprocess_import_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from subprocess import run as execute\nexecute('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding for finding in findings)


def test_rejects_os_system(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import os\nos.system('echo unsafe')\n")
    assert any("os.system()" in finding for finding in findings)


def test_rejects_os_alias_system(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import os as operating_system\noperating_system.system('echo unsafe')\n",
    )
    assert any("os.system()" in finding for finding in findings)


def test_rejects_assigned_os_system_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import os\nexecute = os.system\nexecute('echo unsafe')\n",
    )
    assert any("os.system()" in finding for finding in findings)


def test_rejects_os_popen(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import os\nos.popen('echo unsafe')\n")
    assert any("os.popen()" in finding for finding in findings)


def test_rejects_direct_os_popen_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from os import popen as execute\nexecute('echo unsafe')\n",
    )
    assert any("os.popen()" in finding for finding in findings)


def test_rejects_asyncio_subprocess_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import asyncio\nasyncio.create_subprocess_shell('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)


def test_rejects_asyncio_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import asyncio as aio\naio.create_subprocess_shell('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)


def test_rejects_direct_asyncio_shell_import(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from asyncio import create_subprocess_shell as execute\nexecute('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)


def test_rejects_assigned_asyncio_shell_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import asyncio\nspawn = asyncio.create_subprocess_shell\nspawn('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)
