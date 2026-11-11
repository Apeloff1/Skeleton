from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_dynamic_import_safety as scanner
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
    monkeypatch.setattr(scanner, "BACKEND_ROOT", tmp_path / "missing-backend")

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


def test_discovery_rejects_symlink_directories(tmp_path: Path) -> None:
    root = tmp_path / "backend"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (external / "hidden.py").write_text("value = 2\n", encoding="utf-8")
    link = root / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    with pytest.raises(scanner.DynamicImportScanError, match="source symlink encountered"):
        list(scanner.python_files(root))


def test_discovery_rejects_symlinked_python_files(tmp_path: Path) -> None:
    root = tmp_path / "backend"
    external = tmp_path / "external.py"
    root.mkdir()
    external.write_text("value = 2\n", encoding="utf-8")
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    link = root / "linked.py"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")

    with pytest.raises(scanner.DynamicImportScanError, match="source symlink encountered"):
        list(scanner.python_files(root))


@pytest.mark.parametrize(
    "primitive,bootstrap,loader",
    [
        ("importlib.import_module", "import importlib\n", "importlib.import_module"),
        ("__import__", "", "__import__"),
    ],
)
def test_rejects_long_reverse_order_alias_chain(
    tmp_path: Path, primitive: str, bootstrap: str, loader: str,
) -> None:
    # Reverse declaration order needs >6 closure rounds; a fixed iteration
    # ceiling previously let runtime-selected imports escape the gate.
    aliases = "\n".join(f"loader_{i} = loader_{i + 1}" for i in range(20))
    source = bootstrap + aliases + f"\nloader_20 = {loader}\nmodule = loader_0(chosen)\n"
    assert _unsafe(_scan(tmp_path, source), primitive)


def test_rejects_long_reverse_order_module_alias_chain(tmp_path: Path) -> None:
    aliases = "\n".join(f"module_{i} = module_{i + 1}" for i in range(20))
    source = (
        "import importlib as original\n"
        + aliases
        + "\nmodule_20 = original\nresult = module_0.import_module(chosen)\n"
    )
    assert _unsafe(_scan(tmp_path, source), "importlib.import_module")


def test_deep_literal_alias_remains_allowed(tmp_path: Path) -> None:
    aliases = "\n".join(f"loader_{i} = loader_{i + 1}" for i in range(20))
    source = (
        "import importlib\n"
        + aliases
        + '\nloader_20 = importlib.import_module\nresult = loader_0("json")\n'
    )
    assert _scan(tmp_path, source) == []


def test_conflicting_import_alias_bindings_fail_closed(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import importlib\n"
        "loader = importlib.import_module\n"
        "loader = __import__\n"
        "result = loader(selected)\n",
    )
    assert len(findings) == 1
    assert "alias propagation did not converge" in findings[0]


def test_unrelated_alias_cycle_terminates_without_false_positive(tmp_path: Path) -> None:
    source = (
        "import importlib\n"
        "left = right\n"
        "right = left\n"
        'result = importlib.import_module("json")\n'
    )
    assert _scan(tmp_path, source) == []


@pytest.mark.parametrize(
    "module_import,method,primitive",
    [
        ("import importlib as module", "import_module", "importlib.import_module"),
        ("import builtins as module", "__import__", "__import__"),
    ],
)
def test_rebound_module_alias_cannot_hide_callable(
    tmp_path: Path, module_import: str, method: str, primitive: str,
) -> None:
    # The module alias is later rebound to the import callable. A further
    # alias must retain callable provenance even if the same name was a module.
    source = (
        f"{module_import}\n"
        f"load = module.{method}\n"
        "module = load\n"
        "forwarded = module\n"
        "result = forwarded(chosen)\n"
    )
    assert _unsafe(_scan(tmp_path, source), primitive)


@pytest.mark.parametrize(
    "bootstrap,primitive",
    [
        (
            "import importlib as shared\n"
            "from importlib import import_module as shared\n",
            "importlib.import_module",
        ),
        (
            "import builtins as shared\n"
            "from builtins import __import__ as shared\n",
            "__import__",
        ),
    ],
)
def test_import_binding_collision_preserves_callable_provenance(
    tmp_path: Path, bootstrap: str, primitive: str,
) -> None:
    assert _unsafe(_scan(tmp_path, bootstrap + "forwarded = shared\nforwarded(chosen)\n"), primitive)
