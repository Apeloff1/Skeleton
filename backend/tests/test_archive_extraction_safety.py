from __future__ import annotations

from pathlib import Path

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


def test_rejects_constructor_alias_reused_as_tarfile_handle(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "opener = tarfile.open\n"
        "opener = opener('bundle.tar')\n"
        "opener.extractall('/tmp/out')\n",
    )
    assert _unsafe(findings)


def test_allows_constructor_alias_reused_as_tarfile_handle_with_data_filter(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\n"
        "opener = tarfile.open\n"
        "opener = opener('bundle.tar')\n"
        "opener.extractall('/tmp/out', filter='data')\n",
    )
    assert findings == []


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


def test_allows_tarfile_data_filter_callable(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import tarfile\nwith tarfile.open('bundle.tar') as archive:\n    archive.extractall('/tmp/out', filter=tarfile.data_filter)\n",
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
