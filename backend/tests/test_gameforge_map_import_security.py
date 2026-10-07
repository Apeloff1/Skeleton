from __future__ import annotations

from pathlib import Path

from scripts.check_dynamic_import_safety import violations


def test_gameforge_map_has_no_runtime_selected_python_imports() -> None:
    route = Path(__file__).resolve().parents[1] / "routes" / "gameforge_map.py"
    assert violations(route) == []


def test_gameforge_map_uses_static_module_loader_allowlist() -> None:
    route = Path(__file__).resolve().parents[1] / "routes" / "gameforge_map.py"
    source = route.read_text(encoding="utf-8")
    assert "_MODULE_LOADERS" in source
    assert "__import__(" not in source
    assert "importlib.import_module" not in source
