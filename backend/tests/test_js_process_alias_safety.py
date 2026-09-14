from __future__ import annotations

from pathlib import Path

from scripts.check_js_process_alias_safety import violations


def _scan(tmp_path: Path, source: str, suffix: str = ".ts") -> list[str]:
    path = tmp_path / f"sample{suffix}"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_esm_namespace_exec_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\ncp.exec(userInput);\n",
    )
    assert any("cp.exec()/execSync() is forbidden" in finding for finding in findings)


def test_rejects_esm_namespace_exec_sync_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as processTools from 'child_process';\nprocessTools.execSync(command);\n",
    )
    assert any("processTools.exec()/execSync() is forbidden" in finding for finding in findings)


def test_rejects_commonjs_namespace_exec_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "const cp = require('child_process');\ncp.exec(command);\n",
        suffix=".js",
    )
    assert any("cp.exec()/execSync() is forbidden" in finding for finding in findings)


def test_allows_namespace_spawn_without_shell_exec(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\ncp.spawn(binary, args, { shell: false });\n",
    )
    assert findings == []


def test_ignores_alias_calls_in_comments(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\n// cp.exec(userInput);\nconst value = 1;\n",
    )
    assert findings == []


def test_unrelated_exec_method_is_not_flagged(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "const runner = { exec: (value: string) => value };\nrunner.exec(input);\n",
    )
    assert findings == []
