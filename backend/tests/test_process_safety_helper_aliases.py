"""Adversarial coverage for aliases of process-policy helper primitives."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_rejects_getattr_alias_hiding_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nlookup = getattr\nlookup(subprocess, 'run')('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_dynamic_getattr_through_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nlookup = getattr\nname = 'run'\nlookup(subprocess, name)(['python', '--version'])\n",
    )
    assert any("dynamic getattr() on subprocess" in finding for finding in findings)


def test_rejects_vars_alias_hiding_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nnamespace = vars\nnamespace(subprocess)['run']('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_rejects_dynamic_vars_lookup_through_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nnamespace = vars\nname = 'run'\nnamespace(subprocess)[name](['python', '--version'])\n",
    )
    assert any("dynamic namespace lookup on subprocess" in finding for finding in findings)


def test_rejects_partial_alias_hiding_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools\nimport subprocess\nmake = functools.partial\nrunner = make(subprocess.run, shell=True)\nrunner('echo unsafe')\n",
    )
    assert any("subprocess.run partial" in finding and "shell=..." in finding for finding in findings)


def test_allows_helper_aliases_when_shell_policy_is_literal_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools\nimport subprocess\nlookup = getattr\nnamespace = vars\nmake = functools.partial\n"
        "lookup(subprocess, 'run')(['python', '--version'], shell=False)\n"
        "namespace(subprocess)['run'](['python', '--version'], shell=False)\n"
        "runner = make(subprocess.run, shell=False)\nrunner(['python', '--version'])\n",
    )
    assert findings == []
