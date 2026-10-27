"""Lazy public exports may only load reviewed literal module targets."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
NAMESPACES = (
    ("skeleton", "skeleton/__init__.py", "SkeletonError", "import_module"),
    ("skeleton.inference", "skeleton/inference/__init__.py", "InferenceUsage", "import_module"),
    ("skeleton.jeeves.ai", "skeleton/jeeves/ai/__init__.py", "CreatorRunbook", "_import_module"),
    ("skeleton.ai.agents.jeeves.ai", "skeleton/ai/agents/jeeves/ai/__init__.py",
     "CreatorRunbook", "_import_module"),
)


@pytest.mark.parametrize("namespace,path,symbol,importer", NAMESPACES)
def test_dispatch_imports_are_literal_and_match_source_controlled_map(
    namespace: str, path: str, symbol: str, importer: str,
) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_load_reviewed_export_owner"
    )
    calls = [
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == importer
    ]
    assert calls
    assert all(
        isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)
        for call in calls
    ), "an export dispatcher must never derive an executable import target"
    approved = {call.args[0].value for call in calls}
    module = importlib.import_module(namespace)
    owners = module._HOST_EXPORTS.values() if hasattr(module, "_HOST_EXPORTS") else (
        item[0] for item in module._LAZY_EXPORTS.values()
    )
    assert approved == set(owners)


@pytest.mark.parametrize("namespace,path,symbol,importer", NAMESPACES)
def test_approved_symbol_dispatches_one_literal_module(
    namespace: str, path: str, symbol: str, importer: str,
) -> None:
    module = importlib.import_module(namespace)
    marker = object()
    original = module.__dict__.get(symbol)
    existed = symbol in module.__dict__
    try:
        with patch.object(module, importer, return_value=SimpleNamespace(**{symbol: marker})) as load:
            assert module.__getattr__(symbol) is marker
            assert load.call_count == 1
            owner = module._HOST_EXPORTS[symbol] if hasattr(module, "_HOST_EXPORTS") else module._LAZY_EXPORTS[symbol][0]
            assert load.call_args.args[0] == owner
    finally:
        if existed:
            module.__dict__[symbol] = original
        else:
            module.__dict__.pop(symbol, None)


@pytest.mark.parametrize("namespace,path,symbol,importer", NAMESPACES)
def test_unknown_export_never_executes_import(
    namespace: str, path: str, symbol: str, importer: str,
) -> None:
    module = importlib.import_module(namespace)
    with patch.object(module, importer) as loader:
        with pytest.raises(AttributeError):
            module.__getattr__("unregistered_dynamic_export")
    loader.assert_not_called()


@pytest.mark.parametrize("namespace,path,symbol,importer", NAMESPACES)
def test_corrupted_export_owner_fails_closed_before_import(
    namespace: str, path: str, symbol: str, importer: str,
) -> None:
    module = importlib.import_module(namespace)
    exports = module._HOST_EXPORTS if hasattr(module, "_HOST_EXPORTS") else module._LAZY_EXPORTS
    saved = exports[symbol]
    try:
        exports[symbol] = "unsafe.module" if hasattr(module, "_HOST_EXPORTS") else ("unsafe.module", symbol)
        with patch.object(module, importer) as loader:
            with pytest.raises(ImportError, match="unregistered lazy export owner"):
                module.__getattr__(symbol)
        loader.assert_not_called()
    finally:
        exports[symbol] = saved
