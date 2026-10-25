"""Pin closed lazy-export dispatch to repository-owned literal module targets.

The canonical dynamic-import gate remains unchanged: only the eager call sites
are converted to a statically reviewable, lazy, deny-by-default dispatcher.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "skeleton_repo_dynamic_import_audit", ROOT / "scripts/check_repository_dynamic_import_safety.py"
)
assert spec is not None and spec.loader is not None
SCANNER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SCANNER)

TARGETS = (
    ("skeleton/__init__.py", "_LAZY_EXPORTS", "tuple"),
    ("skeleton/ai/agents/jeeves/ai/__init__.py", "_HOST_EXPORTS", "string"),
    ("skeleton/jeeves/ai/__init__.py", "_HOST_EXPORTS", "string"),
    ("skeleton/ai/game_builder/__init__.py", "_KNOWLEDGE_EXPORTS", "string"),
    ("skeleton/ai/model_runtime/__init__.py", "_LAZY_EXPORTS", "string"),
    ("skeleton/ai/runtime/inference/core/__init__.py", "_LAZY_EXPORTS", "tuple"),
    ("skeleton/inference/__init__.py", "_LAZY_EXPORTS", "tuple"),
    ("skeleton/ai/training/__init__.py", "_GOVERNANCE_EXPORTS", "string"),
    ("skeleton/ai/runtime/learning_foundation/__init__.py", "_LAZY_EXPORTS", "frozenset"),
    ("skeleton/ai/runtime/training/__init__.py", "_LAZY_EXPORTS", "frozenset"),
    ("skeleton/ai/runtime/inference/__init__.py", "_NATIVE_EXPORTS", "single"),
)


@pytest.mark.parametrize("path,table,mode", TARGETS)
def test_lazy_exports_are_backed_only_by_literal_module_dispatch(path: str, table: str, mode: str) -> None:
    file = ROOT / path
    tree = ast.parse(file.read_text(encoding="utf-8"))
    assignments = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == table for target in node.targets
        )
    ]
    assert len(assignments) == 1, path
    mapping = assignments[0]
    assert isinstance(mapping, ast.Dict), path
    expected: set[str] = set()
    for key, value in zip(mapping.keys, mapping.values):
        if mode == "frozenset":
            assert isinstance(key, ast.Constant) and isinstance(key.value, str)
            assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            assert value.func.id == "frozenset"
            expected.add("." + key.value)
        else:
            if mode == "tuple":
                assert isinstance(value, ast.Tuple) and value.elts
                value = value.elts[0]
            assert isinstance(value, ast.Constant) and isinstance(value.value, str)
            expected.add(value.value)
    assert expected, path
    if mode == "single":
        assert expected == {".native_transformer"}
        dispatcher = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "__getattr__")
    else:
        dispatcher = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_load_trusted_lazy_module")
    literal_calls: set[str] = set()
    for node in ast.walk(dispatcher):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if "import_module" not in node.func.id or not node.args:
            continue
        first = node.args[0]
        assert isinstance(first, ast.Constant) and isinstance(first.value, str)
        literal_calls.add(first.value)
    if mode == "single":
        assert literal_calls == {".native_transformer", ".native_runtime"}
    else:
        assert literal_calls == expected, path
    assert SCANNER.violations(file) == [], path


def test_governed_lazy_alias_mirrors_remain_byte_identical() -> None:
    for canonical, mirror in (
        ("skeleton/ai/agents/jeeves/ai/__init__.py", "skeleton/jeeves/ai/__init__.py"),
        ("skeleton/ai/runtime/inference/core/__init__.py", "skeleton/inference/__init__.py"),
    ):
        assert (ROOT / canonical).read_bytes() == (ROOT / mirror).read_bytes()
