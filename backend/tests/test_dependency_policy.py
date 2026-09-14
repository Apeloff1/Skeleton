from __future__ import annotations

import json
from pathlib import Path

from scripts.check_dependency_policy import frontend_violations, python_violations


def test_python_policy_accepts_exact_pins(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi==1.2.3\nuvicorn[standard]==0.30.0\n", encoding="utf-8")
    assert python_violations(requirements) == []


def test_python_policy_rejects_ranges_and_unpinned_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("cryptography>=46,<47\nrequests\n", encoding="utf-8")
    findings = python_violations(requirements)
    assert len(findings) == 2
    assert all("not exact-pinned" in finding for finding in findings)


def _package(tmp_path: Path, dependency: str, value: str, *, manager: str = "yarn@1.22.22+sha512.test") -> tuple[Path, Path]:
    package = tmp_path / "package.json"
    lock = tmp_path / "yarn.lock"
    package.write_text(
        json.dumps({"packageManager": manager, "dependencies": {dependency: value}}),
        encoding="utf-8",
    )
    lock.write_text("# lock\n", encoding="utf-8")
    return package, lock


def test_frontend_policy_rejects_mutable_alias(tmp_path: Path) -> None:
    package, lock = _package(tmp_path, "example", "latest")
    findings = frontend_violations(package, lock)
    assert any("mutable version" in finding for finding in findings)


def test_frontend_policy_rejects_git_and_url_sources(tmp_path: Path) -> None:
    package, lock = _package(tmp_path, "example", "git+https://example.invalid/repo.git")
    findings = frontend_violations(package, lock)
    assert any("non-registry source" in finding for finding in findings)


def test_frontend_policy_requires_lockfile(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({"packageManager": "yarn@1.22.22+sha512.test", "dependencies": {"react": "19.1.0"}}),
        encoding="utf-8",
    )
    findings = frontend_violations(package, tmp_path / "missing.lock")
    assert any("lockfile is missing" in finding for finding in findings)


def test_frontend_policy_requires_package_manager_integrity(tmp_path: Path) -> None:
    package, lock = _package(tmp_path, "react", "19.1.0", manager="yarn@1.22.22")
    findings = frontend_violations(package, lock)
    assert any("integrity hash" in finding for finding in findings)


def test_frontend_policy_accepts_registry_range_with_lock_and_manager_hash(tmp_path: Path) -> None:
    package, lock = _package(tmp_path, "react", "^19.1.0")
    assert frontend_violations(package, lock) == []
