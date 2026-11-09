from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import check_js_process_alias_safety as scanner
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


def test_rejects_optional_chain_exec_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\ncp?.exec(command);\n",
    )
    assert any("cp.exec()/execSync() is forbidden" in finding for finding in findings)


def test_rejects_bracket_exec_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\ncp['execSync'](command);\n",
    )
    assert any("cp bracket exec()/execSync() is forbidden" in finding for finding in findings)


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


def test_ignores_exec_text_inside_string_data(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\nconst docs = \"cp.exec(userInput)\";\n",
    )
    assert findings == []


def test_ignores_pseudo_import_inside_string_data(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "const docs = \"import * as cp from 'node:child_process'; cp.exec(input);\";\n",
    )
    assert findings == []


def test_ignores_exec_text_in_template_literal_data(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\nconst docs = `cp.exec(userInput)`;\n",
    )
    assert findings == []


def test_rejects_exec_inside_template_expression(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\nconst output = `${cp.exec(userInput)}`;\n",
    )
    assert any("cp.exec()/execSync() is forbidden" in finding for finding in findings)


def test_rejects_exec_inside_nested_template_expression(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import * as cp from 'node:child_process';\nconst output = `${`nested ${cp.exec(userInput)}`}`;\n",
    )
    assert any("cp.exec()/execSync() is forbidden" in finding for finding in findings)


def test_unrelated_exec_method_is_not_flagged(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "const runner = { exec: (value: string) => value };\nrunner.exec(input);\n",
    )
    assert findings == []


def test_read_failure_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "blocked.ts"
    source.write_text("export const value = 1;\n", encoding="utf-8")
    real_read_text = Path.read_text

    def blocked_read_text(self: Path, *args, **kwargs):
        if self == source:
            raise PermissionError("SECRET_JS_ALIAS_READ_DETAIL")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked_read_text)
    findings = scanner.violations(source)

    assert findings == [f"{source}: read failure: PermissionError"]
    assert "SECRET_JS_ALIAS_READ_DETAIL" not in findings[0]


def test_missing_frontend_root_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(scanner, "FRONTEND_ROOT", tmp_path / "missing-frontend")

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "JavaScript child_process alias scan failed: FileNotFoundError" in captured.err
    assert "missing-frontend" not in captured.err


def test_nested_enumeration_failure_fails_closed_and_redacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frontend = tmp_path / "frontend"
    blocked = frontend / "blocked"
    blocked.mkdir(parents=True)
    (frontend / "safe.ts").write_text("export const safe = true;\n", encoding="utf-8")
    real_scandir = os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("SECRET_JS_ALIAS_TRAVERSAL_DETAIL")
        return real_scandir(path)

    monkeypatch.setattr(scanner, "FRONTEND_ROOT", frontend)
    monkeypatch.setattr(scanner.os, "scandir", guarded_scandir)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "JavaScript child_process alias scan failed: PermissionError" in captured.err
    assert "SECRET_JS_ALIAS_TRAVERSAL_DETAIL" not in captured.err


def test_zero_file_scan_cannot_report_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    monkeypatch.setattr(scanner, "FRONTEND_ROOT", frontend)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "no frontend JS/TS files were scanned" in captured.err


def test_symlink_scan_root_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    link_root = tmp_path / "frontend-link"
    try:
        link_root.symlink_to(real_root, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    monkeypatch.setattr(scanner, "FRONTEND_ROOT", link_root)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "JavaScript child_process alias scan failed: OSError" in captured.err


def test_discovery_fails_closed_on_symlink_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frontend = tmp_path / "frontend"
    external = tmp_path / "external"
    frontend.mkdir()
    external.mkdir()
    (frontend / "safe.ts").write_text("export const safe = true;\n", encoding="utf-8")
    (external / "hidden.ts").write_text(
        "import * as cp from 'child_process';\ncp.exec(input);\n",
        encoding="utf-8",
    )
    link = frontend / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    monkeypatch.setattr(scanner, "FRONTEND_ROOT", frontend)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "JavaScript child_process alias scan failed: OSError" in captured.err
    assert "linked" not in captured.err
    assert "external" not in captured.err


def test_discovery_fails_closed_on_symlink_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    external = tmp_path / "external.ts"
    external.write_text(
        "import * as cp from 'child_process';\ncp.exec(input);\n",
        encoding="utf-8",
    )
    link = frontend / "linked.ts"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")

    monkeypatch.setattr(scanner, "FRONTEND_ROOT", frontend)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "JavaScript child_process alias scan failed: OSError" in captured.err
    assert "linked.ts" not in captured.err
    assert "external.ts" not in captured.err
