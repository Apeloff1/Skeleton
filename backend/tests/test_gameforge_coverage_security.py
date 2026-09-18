from __future__ import annotations

from pathlib import Path

from scripts.check_dynamic_import_safety import violations


def test_gameforge_coverage_does_not_execute_runtime_selected_modules() -> None:
    route = Path(__file__).resolve().parents[1] / "routes" / "gameforge_coverage.py"
    assert violations(route) == []


def test_gameforge_coverage_activation_is_inventory_only() -> None:
    route = Path(__file__).resolve().parents[1] / "routes" / "gameforge_coverage.py"
    source = route.read_text(encoding="utf-8")
    assert "Dynamic activation is disabled" in source
    assert "importlib.import_module" not in source
    assert "__import__(" not in source
