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


TRUSTED_TWIN_PAIRS = (
    ("skeleton/ai/learning/school/runtime_attestation.py", "skeleton/learning/school/runtime_attestation.py",
     "_load_trusted_named_module", (
         "skeleton.learning.school.decision_ledger", "skeleton.ai.learning.school.decision_ledger",
         "skeleton.learning.school.runtime_replay", "skeleton.ai.learning.school.runtime_replay",
         "skeleton.learning.school.runtime_attestation", "skeleton.ai.learning.school.runtime_attestation",
     )),
    ("skeleton/ai/learning/school/runtime_capsule.py", "skeleton/learning/school/runtime_capsule.py",
     "_load_trusted_twin_module", (
         "skeleton.ai.learning.school.decision_ledger", "skeleton.ai.learning.school.runtime_replay",
     )),
    ("skeleton/ai/learning/school/runtime_replay.py", "skeleton/learning/school/runtime_replay.py",
     "_load_trusted_twin_module", (
         "skeleton.ai.learning.school.decision_ledger", "skeleton.ai.learning.school.session_runtime",
         "skeleton.ai.learning.school.runtime_replay",
     )),
    ("skeleton/ai/runtime/observability/slo.py", "skeleton/observability/slo.py",
     "_load_trusted_slo_twin", (
         "skeleton.ai.runtime.observability.slo", "skeleton.observability.slo",
     )),
)


@pytest.mark.parametrize("canonical,mirror,helper,allowed", TRUSTED_TWIN_PAIRS)
def test_trusted_type_mirrors_retain_identical_literal_imports(
    canonical: str, mirror: str, helper: str, allowed: tuple[str, ...]
) -> None:
    source = (ROOT / canonical).read_bytes()
    assert source == (ROOT / mirror).read_bytes()
    tree = ast.parse(source.decode("utf-8"))
    candidates = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == helper]
    assert len(candidates) == 1
    imported: set[str] = set()
    for node in ast.walk(candidates[0]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and (
            node.func.attr == "import_module"
        ):
            assert isinstance(node.args[0], ast.Constant)
            assert isinstance(node.args[0].value, str)
            imported.add(node.args[0].value)
    assert imported == set(allowed)
    assert SCANNER.violations(ROOT / canonical) == []
    assert SCANNER.violations(ROOT / mirror) == []


CATALOG_EXPORTS = (
    ("skeleton/ai/agents/jeeves/game_frontier_book_curriculum.py",
     "skeleton/jeeves/game_frontier_book_curriculum.py", "GENERATIONS", "forge", "_load_known_forge_module"),
    ("skeleton/ai/runtime/organism/operator_cli.py",
     "skeleton/organism/operator_cli.py", "_VIEWS", "views", "_load_organism_view_module"),
    ("skeleton/ai/webcrawler/dragon_mission_catalog.py",
     None, "_SPECS", "mission", "_load_mission_catalog_module"),
    ("skeleton/ai/webcrawler/game_scale_catalog.py",
     None, "_GROUPS", "scale", "_load_game_scale_module"),
)


@pytest.mark.parametrize("path,mirror,registry,kind,helper", CATALOG_EXPORTS)
def test_closed_catalog_dispatch_matches_complete_literal_registry(
    path: str, mirror: str | None, registry: str, kind: str, helper: str
) -> None:
    src = (ROOT / path).read_bytes()
    if mirror is not None:
        assert src == (ROOT / mirror).read_bytes()
        assert SCANNER.violations(ROOT / mirror) == []
    tree = ast.parse(src.decode("utf-8"))
    values = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == registry for t in node.targets)
    ]
    assert len(values) == 1
    data = ast.literal_eval(values[0])
    if kind == "forge":
        expected = {"skeleton.forge." + row[1] for row in data}
    elif kind == "views":
        expected = {row[0] for row in data.values()}
    elif kind == "mission":
        expected = {"." + row[1] for row in data}
    else:
        expected = {"." + row[1] for row in data}
    assert expected
    dispatch = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == helper
    ]
    assert len(dispatch) == 1
    imported = set()
    for node in ast.walk(dispatch[0]):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if "import_module" not in node.func.id:
            continue
        assert node.args and isinstance(node.args[0], ast.Constant)
        assert isinstance(node.args[0].value, str)
        imported.add(node.args[0].value)
    assert imported == expected
    assert SCANNER.violations(ROOT / path) == []
