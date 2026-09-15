from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_boundaries import scan_repository, violations_for_file


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "skeleton" / "testing").mkdir(parents=True)
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    return tmp_path


def _write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_accepts_inward_and_standard_library_imports(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/domain.py", "import json\nfrom skeleton import architecture\n")
    _write(root, "backend/app.py", "from skeleton import architecture\n")
    assert scan_repository(root) == []


def test_rejects_skeleton_importing_backend(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = _write(root, "skeleton/domain.py", "import backend.server\n")
    findings = violations_for_file(path, root)
    assert any("forbidden import 'backend.server'" in finding for finding in findings)


def test_rejects_skeleton_from_backend_import(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = _write(root, "skeleton/domain.py", "from backend.routes import health\n")
    findings = violations_for_file(path, root)
    assert any("forbidden import 'backend.routes'" in finding for finding in findings)


def test_rejects_backend_production_importing_test_roots(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "backend/app.py", "from skeleton.testing import helper\nimport tests.fixtures\n")
    findings = scan_repository(root)
    assert any("skeleton.testing" in finding for finding in findings)
    assert any("tests.fixtures" in finding for finding in findings)


def test_test_trees_are_exempt_from_production_direction_rules(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "skeleton/testing/probe.py", "import backend.server\n")
    _write(root, "backend/tests/probe.py", "import tests.fixtures\n")
    assert scan_repository(root) == []


def test_namespace_matching_does_not_reject_prefix_lookalikes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = _write(root, "skeleton/domain.py", "import backendish\nimport testsmith\n")
    assert violations_for_file(path, root) == []


def test_relative_imports_do_not_cross_repository_roots(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = _write(root, "skeleton/pkg/module.py", "from . import helper\nfrom .. import architecture\n")
    assert violations_for_file(path, root) == []


def test_parse_failure_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = _write(root, "skeleton/broken.py", "def broken(:\n")
    findings = violations_for_file(path, root)
    assert any("parse failure: SyntaxError" in finding for finding in findings)


def test_missing_canonical_root_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "skeleton").mkdir()
    findings = scan_repository(tmp_path)
    assert "backend: missing canonical source root" in findings
