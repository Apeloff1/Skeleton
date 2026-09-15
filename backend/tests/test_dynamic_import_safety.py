from __future__ import annotations

from pathlib import Path

from scripts.check_dynamic_import_safety import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def _unsafe(findings: list[str], primitive: str) -> bool:
    return any(f"{primitive}() module name must be" in finding for finding in findings)


def test_rejects_runtime_selected_builtin_import(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "module = __import__(module_name)\n")
    assert _unsafe(findings, "__import__")


def test_allows_literal_builtin_import(tmp_path: Path) -> None:
    assert _scan(tmp_path, 'module = __import__("json")\n') == []


def test_rejects_builtins_module_import(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import builtins as bi\nmodule = bi.__import__(module_name)\n",
    )
    assert _unsafe(findings, "__import__")


def test_rejects_imported_builtin_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from builtins import __import__ as load_builtin\nmodule = load_builtin(module_name)\n",
    )
    assert _unsafe(findings, "__import__")


def test_rejects_builtins_mapping_import(tmp_path: Path) -> None:
    findings = _scan(tmp_path, 'module = __builtins__["__import__"](module_name)\n')
    assert _unsafe(findings, "__import__")


def test_rejects_runtime_selected_importlib_module(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib\nmodule = importlib.import_module(module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_aliased_importlib_module(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib as il\nmodule = il.import_module(module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_imported_function_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "from importlib import import_module as load_module\nmodule = load_module(module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_assigned_callable_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib\nloader = importlib.import_module\nmodule = loader(module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_transitive_callable_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib as il\nloader = il.import_module\nload_again = loader\nmodule = load_again(module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_assigned_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib\nil = importlib\nmodule = il.import_module(module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_getattr_import_callable(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'import importlib\nloader = getattr(importlib, "import_module")\nmodule = loader(module_name)\n',
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_keyword_runtime_name(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib\nmodule = importlib.import_module(name=module_name)\n",
    )
    assert _unsafe(findings, "importlib.import_module")


def test_rejects_missing_or_empty_module_name(tmp_path: Path) -> None:
    missing = _scan(tmp_path, "__import__()\n")
    empty = _scan(tmp_path, 'import importlib\nimportlib.import_module("")\n')
    assert _unsafe(missing, "__import__")
    assert _unsafe(empty, "importlib.import_module")


def test_allows_literal_importlib_module(tmp_path: Path) -> None:
    source = (
        "import importlib as il\n"
        'one = il.import_module("json")\n'
        "from importlib import import_module as load_module\n"
        'two = load_module("pathlib")\n'
        "loader = il.import_module\n"
        'three = loader("collections")\n'
    )
    assert _scan(tmp_path, source) == []


def test_ignores_unrelated_import_module_method(tmp_path: Path) -> None:
    assert _scan(tmp_path, "plugin.import_module(module_name)\n") == []
