from __future__ import annotations

from pathlib import Path

from scripts.check_dynamic_import_safety import violations


def test_unbulk_has_no_runtime_selected_python_imports() -> None:
    module = Path(__file__).resolve().parents[1] / "core" / "unbulk.py"
    assert violations(module) == []


def test_unbulk_does_not_expose_unrestricted_lazy_importer() -> None:
    module = Path(__file__).resolve().parents[1] / "core" / "unbulk.py"
    source = module.read_text(encoding="utf-8")
    assert "def lazy_import(" not in source
    assert "class _LazyModule" not in source
    assert "importlib.import_module" not in source
