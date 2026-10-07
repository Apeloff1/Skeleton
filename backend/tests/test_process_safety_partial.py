"""Focused regressions for functools.partial process-call provenance."""

from __future__ import annotations

from pathlib import Path

from scripts import check_process_safety as gate


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return gate.violations(target)


def test_allows_partial_subprocess_with_literal_shell_false(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools\nimport subprocess\nrunner = functools.partial(subprocess.run, shell=False)\nrunner(['python', '--version'])\n",
    )
    assert findings == []


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


def test_rejects_partial_subprocess_with_shell_true(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools\nimport subprocess\nrunner = functools.partial(subprocess.run, shell=True)\nrunner('echo unsafe')\n",
    )
    assert any("partial(..., shell=...)" in finding for finding in findings)


def test_rejects_partial_subprocess_with_dynamic_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from functools import partial\nimport subprocess\nuse_shell = False\nrunner = partial(subprocess.run, shell=use_shell)\n",
    )
    assert any("partial(..., shell=...)" in finding for finding in findings)


def test_rejects_partial_subprocess_with_opaque_kwargs(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from functools import partial\nimport subprocess\noptions = {'shell': False}\nrunner = partial(subprocess.run, **options)\n",
    )
    assert any("partial(..., **kwargs)" in finding for finding in findings)


def test_rejects_shell_true_at_callsite_through_partial_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from functools import partial as bind\nimport subprocess\nrunner = bind(subprocess.run)\nrunner('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.run" in finding and "shell=..." in finding for finding in findings)


def test_tracks_direct_partial_invocation(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import functools as ft\nimport subprocess\nft.partial(subprocess.Popen)('echo unsafe', shell=True)\n",
    )
    assert any("subprocess.Popen" in finding and "shell=..." in finding for finding in findings)


def test_tracks_partial_wrapped_os_system(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from functools import partial\nimport os\nexecute = partial(os.system)\nexecute('echo unsafe')\n",
    )
    assert any("os.system()" in finding for finding in findings)


def test_tracks_partial_wrapped_asyncio_shell(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from functools import partial\nimport asyncio\nspawn = partial(asyncio.create_subprocess_shell)\nspawn('echo unsafe')\n",
    )
    assert any("asyncio.create_subprocess_shell()" in finding for finding in findings)
