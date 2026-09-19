from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_archive_extraction_safety as scanner
from scripts.check_archive_extraction_safety import repository_violations, violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "archive_case.py"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def _unsafe(findings: list[str]) -> bool:
    return any("must use filter='data'" in finding for finding in findings)


def test_rejects_extractall_without_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\nwith tarfile.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_extract_without_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\narchive = tarfile.open('bundle.tar')\narchive.extract('item', '/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_reassigned_tarfile_handle(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archive = tarfile.open('first.tar')\n"
        "archive = tarfile.open('second.tar')\n"
        "archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_constructor_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "open_tar = tarfile.open\n"
        "archive = open_tar('bundle.tar')\n"
        "archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_reused_constructor_alias_as_tarfile_instance(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archive = tarfile.open\n"
        "archive = archive('bundle.tar')\n"
        "archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_method_alias_after_reused_constructor_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archive = tarfile.open\n"
        "archive = archive('bundle.tar')\n"
        "extract_all = archive.extractall\n"
        "extract_all('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_extraction_method_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "with tarfile.open('bundle.tar') as archive:\n"
        "    extract_all = archive.extractall\n"
        "    extract_all('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_simple_tarfile_handle_alias_without_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "with tarfile.open('bundle.tar') as archive:\n"
        "    alias = archive\n"
        "    alias.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_attribute_bound_tarfile_handle(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "class Holder:\n"
        "    pass\n"
        "holder = Holder()\n"
        "holder.archive = tarfile.open('bundle.tar')\n"
        "holder.archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_walrus_bound_tarfile_handle(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "if archive := tarfile.open('bundle.tar'):\n"
        "    archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_allows_literal_data_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\nwith tarfile.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out', filter='data')\n",
    )
    assert findings == []


def test_allows_reused_constructor_alias_with_literal_data_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archive = tarfile.open\n"
        "archive = archive('bundle.tar')\n"
        "archive.extractall('/tmp/out', filter='data')\n",
    )
    assert findings == []


def test_allows_tarfile_data_filter_callable(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\nwith tarfile.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out', filter=tarfile.data_filter)\n",
    )
    assert findings == []


def test_allows_reused_constructor_method_alias_with_data_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archive = tarfile.open\n"
        "archive = archive('bundle.tar')\n"
        "extract_all = archive.extractall\n"
        "extract_all('/tmp/out', filter=tarfile.data_filter)\n",
    )
    assert findings == []


def test_allows_imported_data_filter_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\nfrom tarfile import data_filter as safe_filter\nwith tarfile.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out', filter=safe_filter)\n",
    )
    assert findings == []


def test_allows_assigned_data_filter_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "safe_filter = tarfile.data_filter\n"
        "with tarfile.open('bundle.tar') as archive:\n"
        "    archive.extractall('/tmp/out', filter=safe_filter)\n",
    )
    assert findings == []


def test_tracks_tarfile_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile as tf\nwith tf.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_dynamic_filter_value(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\nselected_filter = 'data'\nwith tarfile.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out', filter=selected_filter)\n",
    )
    assert _unsafe(findings)


def test_ignores_unrelated_extractall_method(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "class Store:\n    def extractall(self, path):\n        return path\nStore().extractall('/tmp/out')\n",
    )
    assert findings == []


def test_repository_has_no_unsafe_tar_extraction() -> None:
    assert repository_violations() == []


def test_nested_enumeration_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "backend"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    real_scandir = scanner.os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("SECRET_ARCHIVE_PATH")
        return real_scandir(path)

    monkeypatch.setattr(scanner, "BACKEND_ROOT", root)
    monkeypatch.setattr(scanner.os, "scandir", guarded_scandir)

    findings = scanner.repository_violations()
    assert findings == ["scanner coverage failure: source traversal failed"]
    assert "SECRET_ARCHIVE_PATH" not in findings[0]


def test_missing_backend_root_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(scanner, "BACKEND_ROOT", tmp_path / "missing-backend")
    assert scanner.repository_violations() == ["scanner coverage failure: source traversal failed"]


def test_zero_file_scan_cannot_report_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(scanner, "BACKEND_ROOT", tmp_path)
    assert scanner.repository_violations() == [
        "scanner coverage failure: no backend production Python files found"
    ]


def test_parse_failure_reports_exception_class_without_payload(tmp_path: Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:  # SECRET_ARCHIVE_PARSE\n    pass\n", encoding="utf-8")

    findings = scanner.violations(bad)

    assert findings == [f"{bad}: parse failure: SyntaxError"]
    assert "SECRET_ARCHIVE_PARSE" not in findings[0]
    assert "invalid syntax" not in findings[0]


def test_discovery_does_not_follow_symlink_directories(tmp_path: Path) -> None:
    root = tmp_path / "backend"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (external / "hidden.py").write_text(
        "import tarfile\ntarfile.open('x.tar').extractall('/tmp/out')\n",
        encoding="utf-8",
    )
    link = root / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    assert list(scanner.production_python_files(root)) == [root / "safe.py"]



def test_rejects_assigned_tarfile_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archives = tarfile\n"
        "with archives.open('bundle.tar') as archive:\n"
        "    archive.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_rejects_assigned_tarfile_module_alias_chain(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "first = tarfile\n"
        "second = first\n"
        "archive = second.open('bundle.tar')\n"
        "archive.extract('item', '/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_allows_assigned_tarfile_module_alias_with_data_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archives = tarfile\n"
        "with archives.open('bundle.tar') as archive:\n"
        "    archive.extractall('/tmp/out', filter=archives.data_filter)\n",
    )
    assert findings == []


def test_reassigned_tarfile_module_alias_is_not_inferred(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "archives = tarfile\n"
        "archives = custom_archives\n"
        "archives.open('bundle.tar').extractall('/tmp/out')\n",
    )
    assert findings == []
