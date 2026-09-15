from __future__ import annotations

from pathlib import Path

from scripts import check_security_scan_surface as scan_surface


def test_audit_enumerates_regular_files_and_prunes_skipped_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("eval('ignored')\n", encoding="utf-8")

    findings, count = scan_surface.audit_scan_surface(tmp_path)

    assert findings == []
    assert count == 1


def test_walk_error_is_blocking_and_redacts_raw_os_detail(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "visible.py").write_text("print('ok')\n", encoding="utf-8")

    def broken_walk(root, *, topdown, onerror, followlinks):
        del root, topdown, followlinks
        onerror(PermissionError("sensitive traversal detail"))
        yield  # pragma: no cover

    monkeypatch.setattr(scan_surface.os, "walk", broken_walk)

    findings, count = scan_surface.audit_scan_surface(tmp_path)

    assert count == 0
    assert "repository traversal failure: PermissionError" in findings
    assert all("sensitive traversal detail" not in finding for finding in findings)


def test_file_metadata_error_is_blocking_and_sanitized(
    tmp_path: Path, monkeypatch,
) -> None:
    good = tmp_path / "good.py"
    blocked = tmp_path / "blocked.py"
    good.write_text("print('ok')\n", encoding="utf-8")
    blocked.write_text("print('hidden')\n", encoding="utf-8")
    original_lstat = Path.lstat

    def selective_lstat(self: Path, *args, **kwargs):
        if self == blocked:
            raise PermissionError("sensitive metadata detail")
        return original_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", selective_lstat)

    findings, count = scan_surface.audit_scan_surface(tmp_path)

    assert count == 1
    assert any(
        "blocked.py: scanner metadata failure: PermissionError" in finding
        for finding in findings
    )
    assert all("sensitive metadata detail" not in finding for finding in findings)


def test_symlinks_are_not_followed_or_counted(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    link.symlink_to(target)

    findings, count = scan_surface.audit_scan_surface(tmp_path)

    assert findings == []
    assert count == 1


def test_empty_surface_fails_closed(tmp_path: Path) -> None:
    findings, count = scan_surface.audit_scan_surface(tmp_path)

    assert count == 0
    assert "scanner coverage failure: no regular repository files were enumerated" in findings


def test_root_metadata_failure_fails_closed_without_raw_error(
    tmp_path: Path, monkeypatch,
) -> None:
    original_lstat = Path.lstat

    def blocked_root_lstat(self: Path, *args, **kwargs):
        if self == tmp_path:
            raise PermissionError("sensitive root detail")
        return original_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", blocked_root_lstat)

    findings, count = scan_surface.audit_scan_surface(tmp_path)

    assert count == 0
    assert findings == ["scanner root metadata failure: PermissionError"]
    assert all("sensitive root detail" not in finding for finding in findings)
