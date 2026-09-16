from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_workflow_security as scanner


def test_read_failure_is_fail_closed_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "blocked.yml"
    workflow.write_text("name: blocked\n", encoding="utf-8")
    original_read_text = Path.read_text

    def blocked_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == workflow:
            raise PermissionError("SECRET_WORKFLOW_READ_DETAIL")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked_read_text)

    findings = scanner.violations(workflow)

    assert findings == [f"{workflow}: read failure: PermissionError"]
    assert "SECRET_WORKFLOW_READ_DETAIL" not in findings[0]


def test_workflow_directory_enumeration_failure_is_fail_closed_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    real_scandir = scanner.os.scandir

    def guarded_scandir(path: object):
        if Path(path) == workflow_dir:
            raise PermissionError("SECRET_WORKFLOW_DIRECTORY_DETAIL")
        return real_scandir(path)

    monkeypatch.setattr(scanner, "WORKFLOW_DIR", workflow_dir)
    monkeypatch.setattr(scanner.os, "scandir", guarded_scandir)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: workflow source traversal failed" in captured.err
    assert "SECRET_WORKFLOW_DIRECTORY_DETAIL" not in captured.err


def test_zero_workflow_scan_cannot_report_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    monkeypatch.setattr(scanner, "WORKFLOW_DIR", workflow_dir)

    assert scanner.main() == 1
    assert "No GitHub Actions workflows found." in capsys.readouterr().err


def test_symlinked_workflow_source_is_rejected_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    external = tmp_path / "external.yml"
    external.write_text(
        "name: external\non: [push]\npermissions: {}\njobs: {}\n",
        encoding="utf-8",
    )
    link = workflow_dir / "linked.yml"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")

    monkeypatch.setattr(scanner, "WORKFLOW_DIR", workflow_dir)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: workflow source traversal failed" in captured.err
    assert str(external) not in captured.err
