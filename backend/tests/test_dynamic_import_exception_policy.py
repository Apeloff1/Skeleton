from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts import check_dynamic_import_safety as scanner


def _source_file(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "backend" / "sample.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    return path


def _exception(*, expression: str, function: str = "load", days: int = 1):
    return scanner.DynamicImportException(
        function=function,
        primitive="importlib.import_module",
        name_expression=expression,
        expires_on=date.today() + timedelta(days=days),
        rationale="focused regression exception",
    )


def test_exact_unexpired_exception_allows_only_declared_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        "import importlib\n\ndef load(module_name):\n    return importlib.import_module(module_name)\n",
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {"backend/sample.py": (_exception(expression="module_name"),)},
    )

    assert scanner.violations(path) == []


def test_exception_authorizes_only_one_matching_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        (
            "import importlib\n\n"
            "def load(module_name):\n"
            "    first = importlib.import_module(module_name)\n"
            "    second = importlib.import_module(module_name)\n"
            "    return first, second\n"
        ),
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {"backend/sample.py": (_exception(expression="module_name"),)},
    )

    findings = scanner.violations(path)
    assert len(findings) == 1
    assert "importlib.import_module() module name must be" in findings[0]


def test_explicit_duplicate_exceptions_each_authorize_one_matching_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        (
            "import importlib\n\n"
            "def load(module_name):\n"
            "    first = importlib.import_module(module_name)\n"
            "    second = importlib.import_module(module_name)\n"
            "    third = importlib.import_module(module_name)\n"
            "    return first, second, third\n"
        ),
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    exception = _exception(expression="module_name")
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {"backend/sample.py": (exception, exception)},
    )

    findings = scanner.violations(path)
    assert len(findings) == 1
    assert ":6: importlib.import_module() module name must be" in findings[0]


def test_exception_does_not_cover_different_expression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        "import importlib\n\ndef load(other_name):\n    return importlib.import_module(other_name)\n",
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {"backend/sample.py": (_exception(expression="module_name"),)},
    )

    findings = scanner.violations(path)
    assert any("importlib.import_module() module name must be" in finding for finding in findings)


def test_exception_does_not_cover_different_function(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        "import importlib\n\ndef other(module_name):\n    return importlib.import_module(module_name)\n",
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {"backend/sample.py": (_exception(expression="module_name", function="load"),)},
    )

    findings = scanner.violations(path)
    assert any("importlib.import_module() module name must be" in finding for finding in findings)


def test_expired_exception_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        "import importlib\n\ndef load(module_name):\n    return importlib.import_module(module_name)\n",
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {"backend/sample.py": (_exception(expression="module_name", days=-1),)},
    )

    findings = scanner.violations(path)
    assert any("importlib.import_module() module name must be" in finding for finding in findings)


def test_blank_rationale_cannot_authorize_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = _source_file(
        tmp_path,
        "import importlib\n\ndef load(module_name):\n    return importlib.import_module(module_name)\n",
    )
    monkeypatch.setattr(scanner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        scanner,
        "APPROVED_DYNAMIC_IMPORT_EXCEPTIONS",
        {
            "backend/sample.py": (
                scanner.DynamicImportException(
                    function="load",
                    primitive="importlib.import_module",
                    name_expression="module_name",
                    expires_on=date.today() + timedelta(days=1),
                    rationale="   ",
                ),
            )
        },
    )

    findings = scanner.violations(path)
    assert any("importlib.import_module() module name must be" in finding for finding in findings)
