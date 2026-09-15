from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_dynamic_import_safety as scanner


def test_nested_enumeration_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "backend"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")

    real_scandir = scanner.os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("SECRET_DYNAMIC_IMPORT_PATH")
        return real_scandir(path)

    monkeypatch.setattr(scanner, "BACKEND_ROOT", root)
    monkeypatch.setattr(scanner.os, "scandir", guarded_scandir)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err
    assert "SECRET_DYNAMIC_IMPORT_PATH" not in captured.err


def test_missing_backend_root_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing-backend"
    monkeypatch.setattr(scanner, "BACKEND_ROOT", missing)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err


def test_zero_file_scan_cannot_report_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(scanner, "BACKEND_ROOT", tmp_path)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "no backend Python files were scanned" in captured.err


def test_parse_failure_reports_exception_class_without_payload(tmp_path: Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text(
        "def broken(:  # SECRET_DYNAMIC_IMPORT_PARSE_PAYLOAD\n    pass\n",
        encoding="utf-8",
    )

    findings = scanner.violations(bad)

    assert findings == [f"{bad}: parse failure: SyntaxError"]
    assert "SECRET_DYNAMIC_IMPORT_PARSE_PAYLOAD" not in findings[0]
    assert "invalid syntax" not in findings[0]


def test_discovery_does_not_follow_symlink_directories(tmp_path: Path) -> None:
    root = tmp_path / "backend"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (external / "hidden.py").write_text("__import__(module_name)\n", encoding="utf-8")

    link = root / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    paths = list(scanner.python_files(root))

    assert paths == [root / "safe.py"]
