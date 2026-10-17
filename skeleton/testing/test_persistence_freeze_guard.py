"""Persistence freeze guard (TD ruling 3, issue #4122).

``skeleton.persistence`` is the one canonical persistence package.
``skeleton.persist``, ``skeleton.storage`` and ``skeleton.state`` are frozen in
place with a docstring notice until they are migrated (issue #4122):

* every frozen module carries the notice;
* importing them stays warning-free (no behaviour change);
* the canonical package and new app-foundation code never import them.
"""

from __future__ import annotations

import ast
import importlib
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ("persist", "storage", "state")
FROZEN_ROOTS = tuple(f"skeleton/{name}" for name in FROZEN) + (
    "skeleton/ai/runtime/storage",
    "skeleton/ai/runtime/state",
)
# New code lives here and must import only skeleton.persistence.
GUARDED_ROOTS = (
    "skeleton/persistence",
    "skeleton/app_services",
    "skeleton/persistence/app_foundation",
)
NOTICE = "issue #4122"
# Mirror-only module that predates the freeze and is not part of the frozen trio.
NOT_FROZEN = {"skeleton/ai/runtime/state/resilient_cache.py"}


def _py_files(rel_root: str) -> list[Path]:
    base = ROOT / rel_root
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _frozen_import(module: str, level: int) -> str | None:
    if level:
        return None
    for name in FROZEN:
        target = f"skeleton.{name}"
        if module == target or module.startswith(target + "."):
            return target
    return None


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, 0
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            yield node.lineno, module, node.level
            if module == "skeleton" and not node.level:
                for alias in node.names:
                    yield node.lineno, f"skeleton.{alias.name}", 0


@pytest.mark.parametrize("rel_root", FROZEN_ROOTS)
def test_every_frozen_module_carries_the_notice(rel_root: str) -> None:
    files = _py_files(rel_root)
    assert files, rel_root
    missing = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel in NOT_FROZEN:
            continue
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        if NOTICE not in doc or "skeleton.persistence" not in doc:
            missing.append(rel)
    assert missing == []


@pytest.mark.parametrize("name", FROZEN)
def test_frozen_packages_import_without_warnings(name: str) -> None:
    module_name = f"skeleton.{name}"
    saved = {k: v for k, v in sys.modules.items() if k == module_name or k.startswith(module_name + ".")}
    for key in saved:
        del sys.modules[key]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            module = importlib.import_module(module_name)
        assert NOTICE in (module.__doc__ or "")
    finally:
        sys.modules.update(saved)


def test_new_code_imports_only_canonical_persistence() -> None:
    offenders = []
    for rel_root in GUARDED_ROOTS:
        for path in _py_files(rel_root):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for lineno, module, level in _imports(tree):
                hit = _frozen_import(module, level)
                if hit:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {module}")
    assert offenders == [], "frozen packages (issue #4122); import skeleton.persistence instead"


def test_guard_detects_frozen_imports() -> None:
    sample = ast.parse(
        "import skeleton.state\n"
        "from skeleton.storage.cas import ContentDigest\n"
        "from skeleton import persist\n"
        "from skeleton.persistence.core import store\n"
        "import skeleton.statex\n"
        "from . import state\n"
    )
    hits = sorted({h for _, m, lvl in _imports(sample) if (h := _frozen_import(m, lvl))})
    assert hits == ["skeleton.persist", "skeleton.state", "skeleton.storage"]
